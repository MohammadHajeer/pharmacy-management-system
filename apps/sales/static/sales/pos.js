/* POS presentation only. Django owns pricing, totals, stock and payments. */
(() => {
const decimalText = (value) => String(value).replace(/(\.\d*?[1-9])0+$|\.0+$/, "$1");
const completionDisabled = (state) => Object.values(state).some(Boolean);
const reindexLines = (rows) => rows.forEach((row, index) => row.querySelectorAll("[name]").forEach((field) => {
  field.name = field.name.replace(/^lines-\d+-/, `lines-${index}-`);
}));
const lookupOnEnter = (event, lookup) => {
  if (event.key === "Enter" && !event.isComposing) {
    event.preventDefault();
    if (!event.repeat) lookup();
  }
};
// Dependency-free tests can exercise the same presentation helpers as the UI.
if (typeof module !== "undefined") module.exports = { decimalText, completionDisabled, reindexLines, lookupOnEnter };
if (typeof document === "undefined") return;
document.addEventListener("DOMContentLoaded", () => {
  const workspace = document.querySelector("[data-pos]");
  if (!workspace) return;
  const draft = document.querySelector("[data-pos-draft]");
  const lines = document.querySelector("[data-sale-lines]");
  const checkout = document.querySelector("[data-checkout]");
  const checkoutFields = document.querySelector("[data-checkout-fields]");
  const completeButton = document.querySelector("[data-complete-button] button");
  const searchForm = document.querySelector("[data-medicine-search]");
  const barcodeForm = document.querySelector("[data-barcode-search]");
  const search = searchForm?.querySelector("input");
  const barcode = barcodeForm?.querySelector("input");
  const results = document.querySelector("[data-search-results]");
  const lookupStatus = document.querySelector("[data-lookup-status]");
  const recordPayment = checkout?.querySelector('[name="record_payment"]');
  const paymentFields = checkout?.querySelector("[data-payment-fields]");
  const reference = checkout?.querySelector('[name="reference"]');
  const method = checkout?.querySelector('[name="payment_method"]');
  const referenceMethods = JSON.parse(document.getElementById("pos-reference-methods").textContent);
  const medicines = new Map(JSON.parse(document.getElementById("pos-medicines").textContent).map((medicine) => [medicine.id, medicine]));
  const snapshot = () => JSON.stringify([...new FormData(draft)]);
  const initial = snapshot();
  let dirty = workspace.dataset.bound === "true";
  let navigating = false;
  let completing = false;
  let uncertainCompletion = false;
  let nextIndex = lines.children.length;
  let lookupSequence = 0;
  let searchTimer;
  let lookupController;

  const syncPayment = () => {
    if (paymentFields) {
      paymentFields.disabled = !recordPayment.checked;
      paymentFields.hidden = !recordPayment.checked;
      reference.required = recordPayment.checked && referenceMethods.includes(method.value);
    }
    if (completeButton) completeButton.disabled = completionDisabled({
      dirty, completing, uncertainCompletion, permissionDenied: checkoutFields.disabled,
      missingPaymentPermission: checkout.dataset.fullPayment === "true" && !recordPayment,
    });
  };
  const syncDraft = () => {
    dirty = workspace.dataset.bound === "true" || snapshot() !== initial;
    document.querySelector("[data-line-count]").textContent = `${lines.children.length} lines`;
    document.querySelector("[data-empty-cart]").hidden = lines.children.length !== 0;
    if (dirty) {
      const status = document.querySelector("[data-draft-status]");
      if (status) status.textContent = "Unsaved changes — save to refresh totals and enable completion.";
      document.querySelector("[data-summary-note]").textContent = "Last saved totals — do not use for the edited cart";
    }
    syncPayment();
  };
  const setUnitContext = (row, medicine) => {
    const unit = medicine.units.find((candidate) => candidate.id === row.querySelector("select").value);
    if (!unit) return;
    row.querySelector("[data-unit-context]").textContent = `Unit price ${decimalText(unit.selected_unit_price)} ${workspace.dataset.currency} · 1 ${unit.name} = ${decimalText(unit.conversion_to_base)} base units`;
  };
  const invalidateLine = (row) => {
    row.querySelector("[data-line-total]").textContent = "—";
    row.querySelector("[data-line-tax]").textContent = "Tax calculated on save";
  };
  const addMedicine = (medicine, unitId) => {
    medicines.set(medicine.id, medicine);
    const template = document.querySelector("[data-line-template]");
    // Only trusted, server-owned template markup; lookup strings use textContent.
    const fragment = document.createElement("template");
    fragment.innerHTML = template.innerHTML.replaceAll("__prefix__", String(nextIndex++));
    const row = fragment.content.querySelector("[data-sale-line]");
    row.dataset.medicineId = medicine.id;
    row.querySelector("[data-medicine-field]").value = medicine.id;
    row.querySelector("[data-medicine-name]").textContent = medicine.name;
    row.querySelector("[data-remove-line]").setAttribute("aria-label", `Remove ${medicine.name}`);
    const baseUnit = medicine.units.find((unit) => unit.is_base_unit)?.name || "base units";
    row.querySelector("[data-stock-context]").textContent = `Available: ${decimalText(medicine.available_stock_base)} ${baseUnit}${medicine.earliest_expiry_date ? ` · Earliest expiry ${medicine.earliest_expiry_date}` : ""}`;
    const select = row.querySelector("select");
    for (const unit of medicine.units) select.add(new Option(unit.name, unit.id));
    select.value = unitId || medicine.units[0].id;
    row.querySelector('[name$="-quantity"]').value = "1";
    row.querySelector('[name$="-discount_amount"]').value = "0";
    row.querySelector("[data-prescription-warning]").hidden = !medicine.prescription_required;
    setUnitContext(row, medicine);
    lines.append(row);
    document.getElementById("id_lines-TOTAL_FORMS").value = lines.children.length;
    syncDraft();
    lookupStatus.textContent = `${medicine.name} added · ${select.selectedOptions[0].textContent}.`;
    results.replaceChildren();
    if (unitId) { barcode.value = ""; barcode.focus(); }
    else { row.querySelector('[name$="-quantity"]').focus(); row.querySelector('[name$="-quantity"]').select(); }
  };
  const fetchLookup = async (kind) => {
    clearTimeout(searchTimer);
    const input = kind === "barcode" ? barcode : search;
    const value = input.value.trim();
    lookupController?.abort();
    const sequence = ++lookupSequence;
    results.replaceChildren();
    if (!value) { lookupStatus.textContent = "Enter a medicine name or scan a barcode."; return; }
    lookupController = new AbortController();
    lookupStatus.textContent = "Looking up eligible medicines…";
    const url = new URL(kind === "barcode" ? workspace.dataset.barcodeUrl : workspace.dataset.searchUrl, location.origin);
    url.searchParams.set(kind === "barcode" ? "barcode" : "q", value);
    if (kind !== "barcode") url.searchParams.set("limit", "12");
    try {
      const response = await fetch(url, { signal: lookupController.signal, headers: { Accept: "application/json" } });
      if (sequence !== lookupSequence) return;
      if (response.status === 404) { lookupStatus.textContent = "Barcode not found. Check the code or search by medicine name."; return; }
      if (!response.ok || response.redirected) throw new Error("Lookup unavailable. Check your connection or sign-in, then try again.");
      const payload = await response.json();
      if (sequence !== lookupSequence) return;
      if (kind === "barcode") { addMedicine(payload, payload.matched_unit_id); return; }
      lookupStatus.textContent = payload.results.length ? `${payload.results.length} matches shown. Refine the search if needed.` : "No matching active sale medicines. Try another name.";
      for (const medicine of payload.results) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "flex w-full items-center justify-between gap-3 rounded-control border border-line bg-surface px-3 py-3 text-left text-sm hover:border-primary-600 hover:bg-accent-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-600";
        const name = document.createElement("span");
        name.className = "font-semibold text-ink-soft";
        name.textContent = `${medicine.name}${medicine.strength ? ` · ${medicine.strength}` : ""}${medicine.prescription_required ? " · Rx required" : ""}`;
        const stock = document.createElement("span");
        stock.className = "shrink-0 text-xs tabular-nums text-muted";
        stock.textContent = `${decimalText(medicine.available_stock_base)} base units`;
        button.append(name, stock);
        button.addEventListener("click", () => addMedicine(medicine));
        results.append(button);
      }
    } catch (error) {
      if (error.name !== "AbortError" && sequence === lookupSequence) lookupStatus.textContent = "Lookup unavailable. Check your connection or sign-in, then try again.";
    }
  };
  search?.addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    // Invalidate an in-flight result as soon as the user changes the query.
    ++lookupSequence;
    lookupController?.abort();
    if (!event.isComposing) searchTimer = setTimeout(() => fetchLookup("search"), 350);
  });
  search?.addEventListener("compositionend", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => fetchLookup("search"), 350); });
  search?.addEventListener("keydown", (event) => lookupOnEnter(event, () => fetchLookup("search")));
  barcode?.addEventListener("keydown", (event) => lookupOnEnter(event, () => fetchLookup("barcode")));
  searchForm?.addEventListener("submit", (event) => { event.preventDefault(); fetchLookup("search"); });
  barcodeForm?.addEventListener("submit", (event) => { event.preventDefault(); fetchLookup("barcode"); });
  document.addEventListener("keydown", (event) => {
    if (event.altKey && event.key === "/" && search) { event.preventDefault(); search.focus(); }
    if (event.key === "Escape" && results?.contains(document.activeElement)) { results.replaceChildren(); search.focus(); }
  });
  lines.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-remove-line]");
    if (!remove) return;
    remove.closest("[data-sale-line]").remove();
    document.getElementById("id_lines-TOTAL_FORMS").value = lines.children.length;
    syncDraft();
    search?.focus();
  });
  const changed = (event) => {
    const row = event.target.closest("[data-sale-line]");
    if (row) {
      invalidateLine(row);
      const medicine = medicines.get(row.dataset.medicineId);
      if (medicine && event.target.matches("select")) setUnitContext(row, medicine);
    }
    syncDraft();
  };
  draft.addEventListener("input", changed);
  draft.addEventListener("change", changed);
  draft.addEventListener("submit", (event) => {
    if (completing) { event.preventDefault(); return; }
    // The service replaces the complete draft: submit a contiguous formset,
    // never DELETE flags or independently mutated line records.
    reindexLines([...lines.children]);
    document.getElementById("id_lines-TOTAL_FORMS").value = lines.children.length;
    document.getElementById("id_lines-INITIAL_FORMS").value = "0";
    navigating = true;
  });
  recordPayment?.addEventListener("change", syncPayment);
  method?.addEventListener("change", syncPayment);
  checkout?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (completeButton.disabled || completing) return;
    const data = new FormData(checkout);
    const errorBox = document.querySelector("[data-checkout-error]");
    errorBox.hidden = true;
    completing = true;
    const completionController = new AbortController();
    const completionTimeout = setTimeout(() => completionController.abort(), 30000);
    syncPayment();
    completeButton.textContent = "Completing sale…";
    const draftFields = draft.querySelector("fieldset");
    const wasDisabled = draftFields.disabled;
    draftFields.disabled = true;
    checkoutFields.disabled = true;
    if (search) search.disabled = true;
    if (barcode) barcode.disabled = true;
    ++lookupSequence;
    lookupController?.abort();
    results?.replaceChildren();
    try {
      const response = await fetch(checkout.action, { method: "POST", body: data, signal: completionController.signal, headers: { Accept: "application/json" } });
      if (response.redirected || !response.headers.get("content-type")?.includes("application/json")) throw new Error("Completion could not be confirmed. Reload this draft or check Sales invoices before trying again.");
      const payload = await response.json();
      if (!response.ok) {
        if (response.status !== 400) throw new Error("Completion could not be confirmed. Reload this draft or check Sales invoices before trying again.");
        errorBox.textContent = Object.values(payload.errors || {}).flat().join(" ") || "Completion rejected. Review the draft and payment.";
        errorBox.hidden = false;
        errorBox.focus();
      } else {
        // Never allow a second completion if navigation is canceled or delayed.
        uncertainCompletion = true;
        if (document.dispatchEvent(new CustomEvent("pharmanex:before-navigate", { cancelable: true, detail: { url: checkout.dataset.invoiceUrl } }))) {
          navigating = true;
          window.location.assign(checkout.dataset.invoiceUrl);
        } else {
          document.querySelector("[data-checkout-hint]").textContent = "Sale completed. Open Sales invoices to view the issued invoice.";
        }
      }
    } catch (error) {
      uncertainCompletion = true;
      errorBox.textContent = "Completion could not be confirmed. Reload this draft or check Sales invoices before trying again.";
      errorBox.hidden = false;
      errorBox.focus();
    } finally {
      clearTimeout(completionTimeout);
      completing = false;
      draftFields.disabled = wasDisabled;
      checkoutFields.disabled = false;
      if (search) search.disabled = false;
      if (barcode) barcode.disabled = false;
      completeButton.textContent = "Complete sale";
      syncPayment();
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if ((dirty || completing) && !navigating) { event.preventDefault(); event.returnValue = ""; }
  });
  window.addEventListener("pageshow", () => { navigating = false; syncDraft(); });
  syncDraft();
});
})();
