using System;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using RimBridge.Ledger;

namespace RimBridge.Server
{
    /// <summary>Loopback-only HTTP server. Request parsing happens on the listener thread pool; Verse work is marshalled via MainThreadQueue.</summary>
    public sealed class HttpServer
    {
        private readonly int _port;
        private HttpListener? _listener;
        private Thread? _thread;
        public volatile bool Running;

        public HttpServer(int port) { _port = port; }

        public void Start()
        {
            _listener = new HttpListener();
            _listener.Prefixes.Add($"http://127.0.0.1:{_port}/");
            _listener.Prefixes.Add($"http://localhost:{_port}/");
            try { _listener.Start(); }
            catch (Exception ex) { BridgeLog.Error($"cannot listen on port {_port}: {ex.Message}"); return; }
            Running = true;
            _thread = new Thread(Loop) { IsBackground = true, Name = "RimBridge-Http" };
            _thread.Start();
        }

        private void Loop()
        {
            while (Running && _listener != null)
            {
                HttpListenerContext ctx;
                try { ctx = _listener.GetContext(); }
                catch (Exception) { if (Running) Thread.Sleep(100); continue; }
                ThreadPool.QueueUserWorkItem(_ => Handle(ctx));
            }
        }

        private static void Handle(HttpListenerContext ctx)
        {
            var req = ctx.Request;
            var res = ctx.Response;
            try
            {
                string path = req.Url.AbsolutePath;
                if (req.HttpMethod == "OPTIONS") { res.StatusCode = 204; res.Close(); return; }
                if (path == "/health")
                {
                    WriteJson(res, new JObject
                    {
                        ["ok"] = true,
                        ["mainThreadAlive"] = MainThreadQueue.MainThreadAlive,
                        ["frames"] = MainThreadQueue.FrameCount,
                        ["version"] = "0.1.0",
                    });
                    return;
                }
                if (path == "/methods") { WriteJson(res, new JObject { ["ok"] = true, ["result"] = Rpc.Describe() }); return; }
                if (path == "/events")
                {
                    long since = long.TryParse(req.QueryString["since"], out var s) ? s : 0;
                    int limit = int.TryParse(req.QueryString["limit"], out var l) ? l : 500;
                    WriteJson(res, new JObject { ["ok"] = true, ["result"] = EventLedger.Since(since, limit) });
                    return;
                }
                if (path == "/screenshot")
                {
                    var p = new JObject();
                    foreach (string k in req.QueryString.AllKeys) if (k != null) p[k] = req.QueryString[k];
                    var env = Rpc.Dispatch("map.screenshot_bytes", p, 30000);
                    if (!(bool)env["ok"]!) { res.StatusCode = 500; WriteJson(res, env); return; }
                    var bytes = Convert.FromBase64String((string)env["result"]!);
                    res.ContentType = "image/png";
                    res.ContentLength64 = bytes.Length;
                    res.OutputStream.Write(bytes, 0, bytes.Length);
                    res.Close();
                    return;
                }
                if (path == "/rpc" && req.HttpMethod == "POST")
                {
                    string body;
                    using (var sr = new StreamReader(req.InputStream, req.ContentEncoding ?? Encoding.UTF8)) body = sr.ReadToEnd();
                    JObject call;
                    try { call = JObject.Parse(body); }
                    catch (Exception ex) { res.StatusCode = 400; WriteJson(res, new JObject { ["ok"] = false, ["error"] = "bad json: " + ex.Message }); return; }
                    string method = (string?)call["method"] ?? "";
                    var p = call["params"] as JObject;
                    int timeout = (int?)call["timeout_ms"] ?? 30000;
                    WriteJson(res, Rpc.Dispatch(method, p, timeout));
                    return;
                }
                res.StatusCode = 404;
                WriteJson(res, new JObject { ["ok"] = false, ["error"] = "not found" });
            }
            catch (Exception ex)
            {
                try { res.StatusCode = 500; WriteJson(res, new JObject { ["ok"] = false, ["error"] = ex.ToString() }); }
                catch { /* client gone */ }
            }
        }

        private static void WriteJson(HttpListenerResponse res, JToken obj)
        {
            var bytes = Encoding.UTF8.GetBytes(obj.ToString(Formatting.None));
            res.ContentType = "application/json";
            res.ContentEncoding = Encoding.UTF8;
            res.ContentLength64 = bytes.Length;
            res.OutputStream.Write(bytes, 0, bytes.Length);
            res.Close();
        }

        public void Stop()
        {
            Running = false;
            try { _listener?.Stop(); } catch { }
        }
    }
}
