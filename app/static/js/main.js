/* TaxCare – main.js  (shared utilities only, no form logic) */

// Bar chart animation — triggered on hasil page
document.querySelectorAll(".bar-fill[data-width]").forEach(bar => {
  const w = bar.dataset.width;
  setTimeout(() => { bar.style.width = w + "%"; }, 120);
});
