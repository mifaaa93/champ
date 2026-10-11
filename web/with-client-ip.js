const http = require("http");
const https = require("https");

function stamp(req) {
  const raw = req.socket && req.socket.remoteAddress ? String(req.socket.remoteAddress) : "";
  const ip = raw.replace(/^::ffff:/, "");
  if (!ip) return;
  req.headers["x-real-ip"] = ip;
  req.headers["x-forwarded-for"] = ip;
}

function wrap(create) {
  return function patched(options, handler) {
    if (typeof options === "function") {
      handler = options;
      options = undefined;
    }
    const wrapped = (req, res) => {
      stamp(req);
      return handler(req, res);
    };
    if (options === undefined) return create(wrapped);
    return create(options, wrapped);
  };
}

http.createServer = wrap(http.createServer);
https.createServer = wrap(https.createServer);
require("./server.js");
