#!/usr/bin/env node
import net from "node:net";
import readline from "node:readline";

const brokerSocket = process.env.MATVERSE_BROKER_SOCKET;
const tools = [
  "cassandra_propose",
  "cassandra_record_decision",
  "cassandra_release",
  "omega_execute",
  "verify_receipts"
];

const send = (value) => process.stdout.write(JSON.stringify(value) + "\n");
const fail = (id, code, message, data) => ({ jsonrpc: "2.0", id: id ?? null, error: { code, message, ...(data === undefined ? {} : { data }) } });
const ok = (id, result) => ({ jsonrpc: "2.0", id, result });
const toolReply = (value, isError = false) => ({ content: [{ type: "text", text: JSON.stringify(value) }], isError });

function brokerCall(method, params) {
  return new Promise((resolve, reject) => {
    if (!brokerSocket) {
      reject(new Error("MATVERSE_BROKER_SOCKET is not configured"));
      return;
    }
    const client = net.createConnection({ path: brokerSocket });
    let buffer = "";
    const timer = setTimeout(() => {
      client.destroy();
      reject(new Error("broker timeout"));
    }, 30000);
    client.setEncoding("utf8");
    client.once("error", (error) => {
      clearTimeout(timer);
      reject(new Error(`broker unavailable: ${error.message}`));
    });
    client.on("data", (chunk) => {
      buffer += chunk;
      const end = buffer.indexOf("\n");
      if (end < 0) return;
      clearTimeout(timer);
      client.end();
      try {
        const reply = JSON.parse(buffer.slice(0, end));
        if (reply?.status !== "OK") {
          reject(new Error(reply?.error || "broker rejected request"));
          return;
        }
        resolve(reply.result);
      } catch (error) {
        reject(new Error(`invalid broker reply: ${error.message}`));
      }
    });
    client.once("connect", () => client.write(JSON.stringify({ method, params }) + "\n"));
  });
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on("line", async (line) => {
  let request;
  try { request = JSON.parse(line); } catch { send(fail(null, -32700, "Parse error")); return; }
  if (request?.jsonrpc !== "2.0" || typeof request.method !== "string") {
    send(fail(request?.id, -32600, "Invalid Request"));
    return;
  }
  if (request.method === "notifications/initialized") return;
  if (request.method === "initialize") {
    send(ok(request.id, {
      protocolVersion: "2024-11-05",
      capabilities: { tools: {} },
      serverInfo: { name: "matverse-cassandra-omega", version: "0.3.0" }
    }));
    return;
  }
  if (request.method === "tools/list") {
    send(ok(request.id, { tools: tools.map((name) => ({ name, inputSchema: { type: "object" } })) }));
    return;
  }
  if (request.method !== "tools/call") {
    send(fail(request.id, -32601, "Method not found"));
    return;
  }
  const name = request.params?.name;
  if (!tools.includes(name)) {
    send(ok(request.id, toolReply({ code: "tool_not_allowlisted", status: "BLOCK" }, true)));
    return;
  }
  if (!request.params?.arguments || typeof request.params.arguments !== "object") {
    send(fail(request.id, -32602, "Invalid tool arguments"));
    return;
  }
  try {
    const result = await brokerCall(name, request.params.arguments);
    send(ok(request.id, toolReply(result)));
  } catch (error) {
    send(ok(request.id, toolReply({ code: "broker_unavailable_or_blocked", message: error.message }, true)));
  }
});
