function pageText() {
  return document.body ? document.body.innerText : "";
}

function findElements(text) {
  const wanted = text.trim().toLowerCase();
  if (!wanted) return [];
  const all = document.querySelectorAll("button, a, input, textarea, [role='button'], [contenteditable='true']");
  return Array.from(all).filter((el) => {
    const value = (el.innerText || el.value || el.getAttribute("aria-label") || "").trim().toLowerCase();
    return value === wanted || value.includes(wanted);
  });
}

function setEditableValue(element, text) {
  element.focus();
  if (element.isContentEditable) {
    element.textContent = text;
    element.dispatchEvent(new InputEvent("input", {bubbles: true, inputType: "insertText", data: text}));
    return;
  }
  const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
  if (descriptor && descriptor.set) descriptor.set.call(element, text);
  else element.value = text;
  element.dispatchEvent(new Event("input", {bubbles: true}));
  element.dispatchEvent(new Event("change", {bubbles: true}));
}

browser.runtime.onMessage.addListener(async (command) => {
  switch (command.action) {
    case "read_page":
      return {ok: true, url: location.href, title: document.title, text: pageText()};
    case "read_selection":
      return {ok: true, text: window.getSelection().toString()};
    case "find_text": {
      const wanted = command.text || "";
      const page = pageText();
      const index = page.toLowerCase().indexOf(wanted.toLowerCase());
      return {ok: index >= 0, index, text: index >= 0 ? page.slice(Math.max(0, index - 200), index + wanted.length + 200) : ""};
    }
    case "click": {
      const elements = findElements(command.text || "");
      if (!elements.length) return {ok: false, error: "element_not_found"};
      elements[0].click();
      return {ok: true, matched: elements.length};
    }
    case "type_text":
    case "paste_text": {
      const active = document.activeElement;
      if (!active || (!(active instanceof HTMLInputElement) && !(active instanceof HTMLTextAreaElement) && !active.isContentEditable)) {
        return {ok: false, error: "editable_element_not_focused"};
      }
      setEditableValue(active, command.text || "");
      return {ok: true};
    }
    default:
      return {ok: false, error: "unknown_action:" + command.action};
  }
});
