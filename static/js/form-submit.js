document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-submit-form]").forEach((form) => {
    let restore = null;
    let safetyTimer;
    const reset = () => {
      clearTimeout(safetyTimer);
      restore?.();
      restore = null;
    };
    window.addEventListener("pageshow", reset);
    document.addEventListener("pharmanex:navigation-reset", reset);

    form.addEventListener("submit", (event) => {
      if (event.defaultPrevented) return;
      if (form.dataset.submitting === "true") {
        event.preventDefault();
        return;
      }

      const submitButton =
        event.submitter?.matches("[data-submit-button]")
          ? event.submitter
          : form.querySelector("[data-submit-button]");

      if (!submitButton || submitButton.disabled) return;

      const label = submitButton.querySelector("[data-submit-label]");
      const loadingState = submitButton.querySelector("[data-submit-loading]");

      const previous = {
        buttonBusy: submitButton.getAttribute("aria-busy"),
        formBusy: form.getAttribute("aria-busy"),
        labelClass: label?.className,
        loadingClass: loadingState?.className,
      };
      const restoreBusy = (element, value) => {
        if (value === null) element.removeAttribute("aria-busy");
        else element.setAttribute("aria-busy", value);
      };
      restore = () => {
        delete form.dataset.submitting;
        submitButton.disabled = false;
        restoreBusy(submitButton, previous.buttonBusy);
        restoreBusy(form, previous.formBusy);
        if (label) label.className = previous.labelClass;
        if (loadingState) loadingState.className = previous.loadingClass;
        // Re-evaluate dirty forms without discarding any user-entered values.
        form.dispatchEvent(new Event("input", { bubbles: true }));
      };

      form.dataset.submitting = "true";
      submitButton.setAttribute("aria-busy", "true");
      form.setAttribute("aria-busy", "true");
      label?.classList.add("hidden");
      loadingState?.classList.remove("hidden");
      loadingState?.classList.add("inline-flex");
      // Let the browser serialize the submitter's name/value before disabling.
      const currentRestore = restore;
      setTimeout(() => {
        if (restore !== currentRestore) return;
        if (event.defaultPrevented) reset();
        else submitButton.disabled = true;
      }, 0);
      safetyTimer = setTimeout(reset, 15000);
    });
  });
});
