document.addEventListener("DOMContentLoaded", () => {
  let activeModal = null;
  let previousFocus = null;
  let previousBodyStyles = null;

  const focusableSelector = [
    "a[href]",
    "button:not([disabled])",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex='-1'])",
  ].join(",");

  const lockPageScroll = () => {
    const scrollbarWidth = Math.max(
      0,
      window.innerWidth - document.documentElement.clientWidth,
    );
    const computedPaddingRight =
      Number.parseFloat(window.getComputedStyle(document.body).paddingRight) || 0;

    previousBodyStyles = {
      overflow: document.body.style.overflow,
      paddingRight: document.body.style.paddingRight,
    };

    if (scrollbarWidth > 0) {
      document.body.style.paddingRight = `${computedPaddingRight + scrollbarWidth}px`;
    }
    document.body.style.overflow = "hidden";
  };

  const unlockPageScroll = () => {
    if (!previousBodyStyles) return;
    document.body.style.overflow = previousBodyStyles.overflow;
    document.body.style.paddingRight = previousBodyStyles.paddingRight;
    previousBodyStyles = null;
  };

  const closeModal = ({ restoreFocus = true } = {}) => {
    if (!activeModal) return;
    activeModal.hidden = true;
    activeModal.setAttribute("aria-hidden", "true");
    unlockPageScroll();
    if (restoreFocus && previousFocus?.isConnected) {
      previousFocus.focus({ preventScroll: true });
    }
    activeModal = null;
    previousFocus = null;
  };

  const openModal = (modal) => {
    if (!modal || modal === activeModal) return;

    if (activeModal) {
      activeModal.hidden = true;
      activeModal.setAttribute("aria-hidden", "true");
    } else {
      previousFocus = document.activeElement;
      lockPageScroll();
    }

    activeModal = modal;
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    (modal.querySelector("[data-modal-panel]") || modal).focus({
      preventScroll: true,
    });
  };

  document.querySelectorAll("[data-modal-open]").forEach((button) => {
    button.addEventListener("click", () => openModal(document.getElementById(button.dataset.modalOpen)));
  });

  document.querySelectorAll("[data-modal-close]").forEach((button) => {
    button.addEventListener("click", closeModal);
  });

  document.querySelectorAll("[data-modal-backdrop]").forEach((backdrop) => {
    backdrop.addEventListener("click", closeModal);
  });

  document.addEventListener("keydown", (event) => {
    if (!activeModal) return;
    if (event.key === "Escape") {
      closeModal();
      return;
    }
    if (event.key !== "Tab") return;

    const panel = activeModal.querySelector("[data-modal-panel]") || activeModal;
    const focusable = [...activeModal.querySelectorAll(focusableSelector)].filter(
      (element) => element.getClientRects().length > 0,
    );
    if (!focusable.length) {
      event.preventDefault();
      panel.focus({ preventScroll: true });
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (
      event.shiftKey &&
      (document.activeElement === first || document.activeElement === panel)
    ) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
});
