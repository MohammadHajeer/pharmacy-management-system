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

    const dirtyIndicators = form.querySelectorAll("[data-dirty-indicator]");
    const pristineIndicators = form.querySelectorAll("[data-pristine-indicator]");
    const dirtySurfaces = form.querySelectorAll("[data-dirty-surface]");

    const initialState = serializeForm(form);
    const updateSubmitState = () => {
      if (form.dataset.submitting === "true") return;
      const isDirty = serializeForm(form) !== initialState;
      submitButton.disabled = !isDirty;
      form.dataset.dirty = String(isDirty);
      dirtyIndicators.forEach((indicator) => {
        indicator.hidden = !isDirty;
      });
      pristineIndicators.forEach((indicator) => {
        indicator.hidden = isDirty;
      });
      dirtySurfaces.forEach((surface) => {
        surface.dataset.dirty = String(isDirty);
      });
    };

    form.addEventListener("input", updateSubmitState);
    form.addEventListener("change", updateSubmitState);
    form.addEventListener("reset", () => window.requestAnimationFrame(updateSubmitState));
    updateSubmitState();
  });
});
