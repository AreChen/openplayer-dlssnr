"""OpenPlayer native v1 control framing; pixels never enter this channel."""
import json

PROTOCOL = "openplayer-native-v1"
MAX_MESSAGE = 65536


def serve(input_stream, output_stream, handler):
    initialized = False
    previous = 0
    while True:
        line = input_stream.readline(MAX_MESSAGE + 1)
        if not line:
            return
        if len(line) > MAX_MESSAGE or not line.endswith(b"\n"):
            raise ValueError("invalid native control framing")
        request = json.loads(line)
        if (not isinstance(request, dict) or set(request) != {"id", "method", "params"}
                or type(request["id"]) is not int or not previous < request["id"] < 2**64
                or not isinstance(request["method"], str)):
            raise ValueError("invalid native control request")
        previous = request["id"]
        response = {"id": previous}
        try:
            if not initialized:
                if (request["method"] != "host.initialize" or not isinstance(request["params"], dict)
                        or request["params"].get("protocol") != PROTOCOL):
                    raise ValueError("protocol negotiation required")
                initialized = True
                response["result"] = {"protocol": PROTOCOL}
            elif request["method"].startswith("host."):
                raise ValueError("reserved host method")
            else:
                response["result"] = handler(request["method"], request["params"])
        except (ValueError, RuntimeError, OSError) as error:
            response["error"] = str(error)
        data = json.dumps(response, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(data) > MAX_MESSAGE:
            raise ValueError("native response exceeds control limit")
        output_stream.write(data)
        output_stream.flush()
        if "error" in response:
            return
