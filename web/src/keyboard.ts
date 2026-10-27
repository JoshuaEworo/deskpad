/** iOS composition stays local until committed, avoiding duplicated IME characters. */
export function attachKeyboard(
  element: HTMLElement,
  text: (value: string) => void,
  key: (name: string) => void,
) {
  const sentinel = "\u200b";
  let composing = false;
  let committed = "";
  const reset = () => {
    element.textContent = sentinel;
    if (document.activeElement === element) {
      const range = document.createRange();
      range.selectNodeContents(element);
      range.collapse(false);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
  };
  element.addEventListener("focus", reset);
  element.addEventListener("paste", (event) => {
    event.preventDefault();
    const value = event.clipboardData?.getData("text/plain");
    if (value) text(value);
    reset();
  });
  element.addEventListener("compositionstart", () => {
    composing = true;
    committed = "";
  });
  element.addEventListener("compositionend", (event) => {
    composing = false;
    committed = event.data;
    if (event.data) text(event.data);
    reset();
    queueMicrotask(() => {
      committed = "";
    });
  });
  element.addEventListener("beforeinput", (event) => {
    if (composing || event.isComposing) return;
    if (
      event.inputType === "deleteContentBackward" ||
      event.inputType === "deleteContentForward"
    ) {
      event.preventDefault();
      key(event.inputType === "deleteContentBackward" ? "Backspace" : "Delete");
      reset();
    } else if (
      event.inputType === "insertLineBreak" ||
      event.inputType === "insertParagraph"
    ) {
      event.preventDefault();
      key("Enter");
      reset();
    }
  });
  element.addEventListener("input", () => {
    if (composing) return;
    const value = (element.textContent || "").replaceAll(sentinel, "");
    if (committed && value === committed) {
      committed = "";
      reset();
      return;
    }
    committed = "";
    if (value) text(value);
    reset();
  });
  element.addEventListener("keydown", (event) => {
    if (composing || event.isComposing) return;
    if (
      [
        "Enter",
        "Backspace",
        "Delete",
        "Tab",
        "Escape",
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
      ].includes(event.key)
    ) {
      event.preventDefault();
      key(event.key);
      reset();
    }
  });
}
