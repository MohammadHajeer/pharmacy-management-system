document.addEventListener("DOMContentLoaded", () => {
  const serializeForm = (form) => {
    const entries = [];
    new FormData(form).forEach((value, name) => {
      if (value instanceof File) {
        entries.push([name, value.name, value.size, value.lastModified]);
      } else {
        entries.push([name, value]);
      }
    });
    return JSON.stringify(entries);
  };

  document.querySelectorAll("[data-dirty-form]").forEach((form) => {
    const submitButton = form.querySelector("[data-dirty-submit]");
    if (!submitButton) return;

    const initialState = serializeForm(form);
    const updateSubmitState = () => {
      if (form.dataset.submitting === "true") return;
      submitButton.disabled = serializeForm(form) === initialState;
    };

    form.addEventListener("input", updateSubmitState);
    form.addEventListener("change", updateSubmitState);
    form.addEventListener("reset", () => window.requestAnimationFrame(updateSubmitState));
    updateSubmitState();
  });
});
