#!/usr/bin/env node
import readline from "node:readline";

const names = [
  "cassandra_propose",
  "cassandra_record_decision",
  "cassandra_release",
  "omega_execute",
  "verify_receipts"
];

const send = (value) => process.stdout.write(JSON.stringify(value) + "\n");
const fail = (id, code, message) => ({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });
const ok = (id, result) => ({ jsonrpc: "2.0", id, result });

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on("line", (line) => {
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
    send(ok(request.id, { tools: names.map((name) => ({ name, inputSchema: { type: "object" } })) }));
    return;
  }
  if (request.method === "tools/call") {
    const allowed = names.includes(request.params?.name);
    const body = allowed
      ? { code: "broker_transport_not_connected", status: "HOLD" }
      : { code: "tool_not_allowlisted", status: "BLOCK" };
    send(ok(request.id, { content: [{ type: "text", text: JSON.stringify(body) }], isError: true }));
    return;
  }
  send(fail(request.id, -32601, "Method not found"));
});
