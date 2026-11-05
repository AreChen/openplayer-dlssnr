#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mpv/client.h>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <stdexcept>
#include <string>
#include <vector>

static std::string utf8(const wchar_t* text) {
    int size = WideCharToMultiByte(CP_UTF8, 0, text, -1, nullptr, 0, nullptr, nullptr);
    std::string value(size, '\0');
    WideCharToMultiByte(CP_UTF8, 0, text, -1, value.data(), size, nullptr, nullptr);
    value.pop_back();
    return value;
}

template <typename T> static T load(HMODULE dll, const char* name) {
    auto function = reinterpret_cast<T>(GetProcAddress(dll, name));
    if (!function) throw std::runtime_error(name);
    return function;
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 4) { std::fprintf(stderr, "usage: probe libmpv.dll media script [vo]\n"); return 2; }
    // Keep this handle until process exit. A watchdog killing the probe also
    // terminates helpers created by a filter, without touching other processes.
    HANDLE job = CreateJobObjectW(nullptr, nullptr);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!job || !SetInformationJobObject(job, JobObjectExtendedLimitInformation, &limits, sizeof(limits))
        || !AssignProcessToJobObject(job, GetCurrentProcess())) return 3;
    const bool ownedRun = !std::wcscmp(argv[1], L"--owned-run");
    if (ownedRun || !std::wcscmp(argv[1], L"--run")) {
        if (!ownedRun && std::wcscmp(argv[3], L"main") && std::wcscmp(argv[3], L"overlay")
            && std::wcscmp(argv[3], L"overlay-alt-f4")) return 2;
        STARTUPINFOW startup{}; startup.cb = sizeof(startup);
        startup.dwFlags = STARTF_USESTDHANDLES;
        startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
        startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
        startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);
        PROCESS_INFORMATION child{};
        std::wstring line = L"\"" + std::wstring(argv[2]) + L"\" \"" + argv[3] + L"\"";
        if (!CreateProcessW(argv[2], line.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW,
            nullptr, nullptr, &startup, &child)) return 7;
        CloseHandle(child.hThread);
        if (WaitForSingleObject(child.hProcess, 65000) != WAIT_OBJECT_0) return 8;
        DWORD exitCode = 0;
        GetExitCodeProcess(child.hProcess, &exitCode);
        CloseHandle(child.hProcess);
        return static_cast<int>(exitCode);
    }
    // Developer-only explicit preload: no environment or DLL search path changes.
    // Keep VSScript loaded until process exit; its Python globals cannot safely
    // unload/reinitialize during playback. Production must own this lifetime.
    if (argc > 5) {
        if (!LoadLibraryExW(argv[5], nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32)) {
            std::fprintf(stderr, "portable VSScript preload failed: %lu\n", GetLastError());
            return 9;
        }
    }
    auto dll = LoadLibraryW(argv[1]);
    if (!dll) { std::fprintf(stderr, "LoadLibrary failed: %lu\n", GetLastError()); return 4; }
    try {
#define API(name) auto name = load<decltype(&::name)>(dll, #name)
        API(mpv_create); API(mpv_initialize); API(mpv_set_option_string);
        API(mpv_command); API(mpv_wait_event); API(mpv_request_log_messages);
        API(mpv_get_property_string); API(mpv_free); API(mpv_terminate_destroy);
#undef API
        auto handle = mpv_create();
        if (!handle) throw std::runtime_error("mpv_create failed");
        auto option = [&](const char* key, const char* value) {
            if (mpv_set_option_string(handle, key, value) < 0) throw std::runtime_error(key);
        };
        option("config", "no"); option("load-scripts", "no"); option("ao", "null");
        const auto vo = argc > 4 ? utf8(argv[4]) : "null";
        option("vo", vo.c_str()); option("idle", "yes");
        option("keep-open", "yes"); option("hwdec", "no");
        option("screenshot-template", "probe-shot");
        if (mpv_initialize(handle) < 0) throw std::runtime_error("mpv_initialize failed");
        mpv_request_log_messages(handle, "info");
        int failures = 0;
        auto command = [&](std::vector<const char*> args) {
            std::printf("COMMAND %s", args[0]);
            for (size_t i = 1; i < args.size(); ++i) std::printf(" %s", args[i]);
            args.push_back(nullptr);
            const auto code = mpv_command(handle, args.data());
            std::printf(" => %d\n", code); std::fflush(stdout);
            if (code < 0) ++failures;
        };
        auto pump = [&](int milliseconds) {
            auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(milliseconds);
            while (std::chrono::steady_clock::now() < deadline) {
                auto event = mpv_wait_event(handle, 0.02);
                if (event->event_id == MPV_EVENT_LOG_MESSAGE) {
                    auto log = static_cast<mpv_event_log_message*>(event->data);
                    std::printf("LOG %s %s %s", log->prefix, log->level, log->text);
                    if (!std::strcmp(log->level, "error") || !std::strcmp(log->level, "fatal")) ++failures;
                }
            }
            for (auto key : {"time-pos", "eof-reached", "vf"}) {
                auto value = mpv_get_property_string(handle, key);
                std::printf("PROPERTY %s=%s\n", key, value ? value : "unavailable");
                if (value) mpv_free(value);
            }
            std::fflush(stdout);
        };
        const auto script = utf8(argv[3]);
        const auto filter = "@probe:vapoursynth=file=%" + std::to_string(script.size()) + "%" + script + ":concurrent-frames=1";
        const auto media = utf8(argv[2]);
        command({"vf", "add", filter.c_str()});
        command({"loadfile", media.c_str()}); pump(3000);
        command({"set", "pause", "yes"}); pump(150);
        command({"seek", "0.2", "absolute+exact"}); pump(150);
        command({"set", "pause", "no"}); pump(500);
        command({"vf", "remove", "@probe"}); pump(300);
        command({"vf", "add", filter.c_str()}); pump(2000);
        command({"stop"}); pump(100);
        command({"loadfile", media.c_str()}); pump(2500);
        std::puts("DESTROY_BEGIN"); std::fflush(stdout);
        mpv_terminate_destroy(handle);
        std::puts("DESTROY_COMPLETE"); std::fflush(stdout);
        return failures ? 5 : 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "probe error: %s\n", error.what());
        return 6;
    }
}
