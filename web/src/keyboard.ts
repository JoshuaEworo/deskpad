/** iOS composition stays local until committed, avoiding duplicated IME characters. */
export function attachKeyboard(
  element: HTMLTextAreaElement,
  text: (value: string) => void,
  key: (name: string) => void,
) {
  const sentinel = "\u200b";
  let composing = false;
  let committed = "";
  const reset = () => {
    element.value = sentinel;
    element.setSelectionRange(1, 1);
  };
  element.addEventListener("focus", reset);
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
    const value = element.value.replaceAll(sentinel, "");
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
