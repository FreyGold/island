const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "Island.qml"), "utf8");
const handler = source.match(/^  function handlePillNotification\(activate\) \{[\s\S]*?^  \}/m);
assert.ok(handler, "The notification handler must exist");

function click(row, activate) {
  const calls = [];
  const context = {
    feedbackKind: "notification",
    view: "feedback",
    notifications: {
      last: row,
      agent: value => value.agent || "",
      command: (method, value) => calls.push([method, value]),
    },
    addons: {
      root: () => ({ focusSession: value => calls.push(["focusSession", value]) }),
    },
  };
  vm.runInNewContext(handler[0] + ";handlePillNotification(" + activate + ")", context);
  assert.equal(context.view, "rest");
  assert.equal(context.feedbackKind, "");
  return calls;
}

test("Left click invokes the saved crash action", () => {
  const row = { summary: "Process crashed: test-app" };
  assert.deepEqual(click(row, true), [["invokeKey", row]]);
});

test("Right click dismisses without invoking the crash action", () => {
  const row = { summary: "Process crashed: test-app" };
  assert.deepEqual(click(row, false), [["dismissKey", row]]);
});

test("Left click keeps the Codex terminal focus action", () => {
  const row = { agent: "codex", summary: "Codex needs confirmation", body: "Workspace 2 · Example session\nConfirm a command" };
  assert.deepEqual(click(row, true), [["focusSession", "Workspace 2 · Example session"], ["dismissKey", row]]);
});

test("Right click does not focus the Codex terminal", () => {
  const row = { agent: "codex", summary: "Codex needs confirmation" };
  assert.deepEqual(click(row, false), [["dismissKey", row]]);
});

test("An empty notification has no action", () => {
  assert.deepEqual(click(null, true), []);
});
