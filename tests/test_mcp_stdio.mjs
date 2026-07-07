import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { test } from "node:test";

function request(message) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ["scripts/mcp_stdio_server.mjs"], { stdio: ["pipe", "pipe", "pipe"] });
    let output = "";
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => { output += chunk; });
    child.once("error", reject);
    child.stdin.write(JSON.stringify(message) + "\n");
    setTimeout(() => {
      child.kill();
      try { resolve(JSON.parse(output.trim())); } catch (error) { reject(error); }
    }, 150);
  });
}

test("initialize advertises MCP tools", async () => {
  const reply = await request({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} });
  assert.equal(reply.result.serverInfo.name, "matverse-cassandra-omega");
  assert.ok(reply.result.capabilities.tools);
});

test("tools list is exactly the five governed tools", async () => {
  const reply = await request({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });
  const names = reply.result.tools.map((tool) => tool.name).sort();
  assert.deepEqual(names, [
    "cassandra_propose",
    "cassandra_record_decision",
    "cassandra_release",
    "omega_execute",
    "verify_receipts"
  ]);
});

test("direct command is not an allowlisted MCP tool", async () => {
  const reply = await request({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "git", arguments: {} } });
  const payload = JSON.parse(reply.result.content[0].text);
  assert.equal(payload.code, "tool_not_allowlisted");
});
