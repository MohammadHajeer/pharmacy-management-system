document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-submit-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
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

      form.dataset.submitting = "true";
      submitButton.disabled = true;
      submitButton.setAttribute("aria-busy", "true");
      form.setAttribute("aria-busy", "true");
      label?.classList.add("hidden");
      loadingState?.classList.remove("hidden");
      loadingState?.classList.add("inline-flex");
    });
  });
});
