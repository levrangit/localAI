const API = "http://127.0.0.1:8765";
const CLIENT_ID = "firefox-" + Math.random().toString(36).slice(2);

async function poll() {
  try {
    const response = await fetch(API + "/next", {headers: {"X-Client-Id": CLIENT_ID}, cache: "no-store"});
    const data = await response.json();
    if (data.command) await execute(data.command);
  } catch (_) {}
}

async function execute(command) {
  let result;
  try {
    const tabs = await browser.tabs.query({active: true, currentWindow: true});
    if (!tabs.length) throw new Error("active tab not found");
    const tab = tabs[0];

    if (command.action === "get_active_tab") {
      result = {id: command.id, ok: true, url: tab.url || "", title: tab.title || "", tab_id: tab.id};
    } else {
      result = await browser.tabs.sendMessage(tab.id, {
        action: command.action,
        text: command.text || "",
        selector: command.selector || ""
      });
      result.id = command.id;
    }
  } catch (error) {
    result = {id: command.id, ok: false, error: String(error)};
  }

  await fetch(API + "/result", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(result)
  });
}

setInterval(poll, 300);
poll();
