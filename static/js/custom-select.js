document.addEventListener("DOMContentLoaded", () => {
  let openSelect = null;

  const closeSelect = (select) => {
    if (!select) return;

    select.menu.hidden = true;
    select.trigger.setAttribute("aria-expanded", "false");
    select.trigger.removeAttribute("aria-activedescendant");
    select.chevron?.classList.remove("rotate-180");
    select.activeIndex = -1;

    if (openSelect === select) openSelect = null;
  };

  const closeOpenSelect = () => closeSelect(openSelect);

  document.querySelectorAll("[data-custom-select]").forEach((root) => {
    const native = root.querySelector("[data-custom-select-native]");
    const ui = root.querySelector("[data-custom-select-ui]");
    const trigger = root.querySelector("[data-custom-select-trigger]");
    const triggerValue = root.querySelector("[data-custom-select-value]");
    const menu = root.querySelector("[data-custom-select-menu]");
    const nativeIcon = root.querySelector("[data-custom-select-native-icon]");
    const options = Array.from(root.querySelectorAll("[data-custom-select-option]"));
    const label = root.closest("[data-custom-select-root]")?.querySelector("label");

    if (!native || !ui || !trigger || !triggerValue || !menu) return;

    const select = {
      root,
      native,
      ui,
      trigger,
      triggerValue,
      menu,
      options,
      chevron: trigger.querySelector("svg"),
      activeIndex: -1,
    };

    const enabledOptionIndexes = () =>
      options
        .map((option, index) => (option.disabled ? -1 : index))
        .filter((index) => index >= 0);

    const setActiveIndex = (index) => {
      options.forEach((option, optionIndex) => {
        option.classList.toggle("bg-surface-hover", optionIndex === index);
      });

      select.activeIndex = index;
      const activeOption = options[index];
      if (!activeOption) {
        trigger.removeAttribute("aria-activedescendant");
        return;
      }

      trigger.setAttribute("aria-activedescendant", activeOption.id);
      activeOption.scrollIntoView({ block: "nearest" });
    };

    const syncFromNative = () => {
      const selectedNativeOption = native.options[native.selectedIndex];
      const selectedValue = native.value;
      const displayValue = selectedNativeOption?.textContent?.trim() || ui.dataset.placeholder;

      triggerValue.textContent = displayValue;
      triggerValue.classList.toggle("text-muted", selectedValue === "");
      triggerValue.classList.toggle("text-ink", selectedValue !== "");
      trigger.disabled = native.disabled;

      options.forEach((option) => {
        const selected = option.dataset.value === selectedValue;
        option.setAttribute("aria-selected", String(selected));
        option.classList.toggle("bg-accent-soft", selected);
        option.classList.toggle("text-accent", selected);
        option.querySelector("[data-custom-select-indicator]")?.classList.toggle("hidden", !selected);
      });

      if (native.validity.valid) trigger.removeAttribute("aria-invalid");
    };

    const open = () => {
      if (native.disabled) return;
      if (openSelect && openSelect !== select) closeSelect(openSelect);

      menu.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      select.chevron?.classList.add("rotate-180");
      openSelect = select;

      const selectedIndex = options.findIndex(
        (option) => !option.disabled && option.dataset.value === native.value,
      );
      const firstEnabledIndex = enabledOptionIndexes()[0] ?? -1;
      setActiveIndex(selectedIndex >= 0 ? selectedIndex : firstEnabledIndex);
    };

    const moveActive = (direction) => {
      const indexes = enabledOptionIndexes();
      if (!indexes.length) return;

      const position = indexes.indexOf(select.activeIndex);
      const nextPosition = position < 0
        ? direction > 0 ? 0 : indexes.length - 1
        : (position + direction + indexes.length) % indexes.length;
      setActiveIndex(indexes[nextPosition]);
    };

    const chooseOption = (option) => {
      if (!option || option.disabled) return;

      native.value = option.dataset.value;
      native.dispatchEvent(new Event("change", { bubbles: true }));
      syncFromNative();
      closeSelect(select);
      trigger.focus();
    };

    native.classList.add("sr-only");
    native.tabIndex = -1;
    native.setAttribute("aria-hidden", "true");
    if (nativeIcon) nativeIcon.hidden = true;
    ui.hidden = false;
    syncFromNative();

    label?.addEventListener("click", (event) => {
      event.preventDefault();
      trigger.focus();
    });

    trigger.addEventListener("click", () => {
      if (trigger.getAttribute("aria-expanded") === "true") {
        closeSelect(select);
      } else {
        open();
      }
    });

    trigger.addEventListener("keydown", (event) => {
      const isOpen = trigger.getAttribute("aria-expanded") === "true";

      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!isOpen) open();
        moveActive(event.key === "ArrowDown" ? 1 : -1);
      } else if (event.key === "Home" && isOpen) {
        event.preventDefault();
        setActiveIndex(enabledOptionIndexes()[0] ?? -1);
      } else if (event.key === "End" && isOpen) {
        event.preventDefault();
        setActiveIndex(enabledOptionIndexes().at(-1) ?? -1);
      } else if ((event.key === "Enter" || event.key === " ") && isOpen) {
        event.preventDefault();
        chooseOption(options[select.activeIndex]);
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        open();
      } else if (event.key === "Escape" && isOpen) {
        event.preventDefault();
        closeSelect(select);
      } else if (event.key === "Tab") {
        closeSelect(select);
      }
    });

    options.forEach((option, index) => {
      option.addEventListener("click", () => chooseOption(option));
      option.addEventListener("mousemove", () => {
        if (!option.disabled && select.activeIndex !== index) setActiveIndex(index);
      });
    });

    native.addEventListener("change", syncFromNative);
    native.addEventListener("invalid", (event) => {
      event.preventDefault();
      trigger.setAttribute("aria-invalid", "true");
      trigger.focus();
    });
    native.form?.addEventListener("reset", () => window.requestAnimationFrame(syncFromNative));
  });

  document.addEventListener("pointerdown", (event) => {
    if (openSelect && !openSelect.root.contains(event.target)) closeOpenSelect();
  });
});
