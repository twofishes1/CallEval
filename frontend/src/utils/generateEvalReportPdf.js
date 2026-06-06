import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";

const MARGIN_MM = 12;
const SECTION_GAP_MM = 3;

function waitForPaint() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  });
}

async function withCaptureEnvironment(stack, fn) {
  document.body.classList.add("eval-report-pdf-exporting");
  if (stack) {
    stack.classList.add("eval-report-pdf-capturing");
  }
  await waitForPaint();
  await new Promise((r) => setTimeout(r, 160));
  try {
    return await fn();
  } finally {
    if (stack) {
      stack.classList.remove("eval-report-pdf-capturing");
    }
    document.body.classList.remove("eval-report-pdf-exporting");
  }
}

/**
 * Slice a tall canvas into page-sized strips (avoids duplicate/overlap from negative Y offset).
 */
function addCanvasSlicedPages(pdf, canvas, contentW, startY = MARGIN_MM) {
  const pageH = pdf.internal.pageSize.getHeight();
  const contentHmm = pageH - MARGIN_MM * 2;
  const scale = contentW / canvas.width;
  const slicePx = Math.max(1, Math.floor(contentHmm / scale));

  let srcY = 0;
  let cursorY = startY;
  let isFirstSlice = true;

  while (srcY < canvas.height) {
    const sliceH = Math.min(slicePx, canvas.height - srcY);
    const sliceCanvas = document.createElement("canvas");
    sliceCanvas.width = canvas.width;
    sliceCanvas.height = sliceH;
    const ctx = sliceCanvas.getContext("2d");
    if (!ctx) break;
    ctx.drawImage(canvas, 0, srcY, canvas.width, sliceH, 0, 0, canvas.width, sliceH);

    const sliceHmm = sliceH * scale;
    const remaining = pageH - MARGIN_MM - cursorY;

    if (sliceHmm > remaining - 1 && !isFirstSlice) {
      pdf.addPage();
      cursorY = MARGIN_MM;
    } else if (sliceHmm > remaining - 1 && isFirstSlice && cursorY > MARGIN_MM + 2) {
      pdf.addPage();
      cursorY = MARGIN_MM;
    }

    pdf.addImage(
      sliceCanvas.toDataURL("image/png"),
      "PNG",
      MARGIN_MM,
      cursorY,
      contentW,
      sliceHmm,
    );

    srcY += sliceH;
    cursorY += sliceHmm + SECTION_GAP_MM;
    isFirstSlice = false;

    if (srcY < canvas.height) {
      pdf.addPage();
      cursorY = MARGIN_MM;
    }
  }

  const pageH2 = pdf.internal.pageSize.getHeight();
  if (cursorY > pageH2 - MARGIN_MM - 8) {
    return MARGIN_MM;
  }
  return cursorY;
}

async function captureElement(el, scale = 2) {
  const rect = el.getBoundingClientRect();
  if (rect.width < 1 || rect.height < 1) {
    const label = el.querySelector("h2, h1")?.textContent?.trim() || "unknown section";
    throw new Error(`PDF 截图失败（区域为空）：${label}`);
  }
  const canvas = await html2canvas(el, {
    scale,
    useCORS: true,
    logging: false,
    backgroundColor: "#ffffff",
    width: el.scrollWidth,
    height: el.scrollHeight,
    windowWidth: el.scrollWidth,
    windowHeight: el.scrollHeight,
    scrollX: 0,
    scrollY: 0,
    onclone: (clonedDoc) => {
      clonedDoc.querySelectorAll(".eval-report-pdf-stack").forEach((node) => {
        node.style.left = "0";
        node.style.opacity = "1";
      });
    },
  });
  if (canvas.height < 2) {
    const label = el.querySelector("h2, h1")?.textContent?.trim() || "unknown section";
    throw new Error(`PDF 截图失败（高度为 0）：${label}`);
  }
  return canvas;
}

/**
 * Export report section-by-section to avoid cutting tables mid-row.
 */
async function appendCanvasToPdf(pdf, canvas, contentW, cursorY) {
  const pageH = pdf.internal.pageSize.getHeight();
  const contentHmm = pageH - MARGIN_MM * 2;
  const imgHmm = (canvas.height * contentW) / canvas.width;
  const remaining = pageH - MARGIN_MM - cursorY;

  if (imgHmm <= remaining - 1) {
    pdf.addImage(canvas.toDataURL("image/png"), "PNG", MARGIN_MM, cursorY, contentW, imgHmm);
    return cursorY + imgHmm + SECTION_GAP_MM;
  }

  if (cursorY > MARGIN_MM + 2 && imgHmm <= contentHmm) {
    pdf.addPage();
    pdf.addImage(canvas.toDataURL("image/png"), "PNG", MARGIN_MM, MARGIN_MM, contentW, imgHmm);
    return MARGIN_MM + imgHmm + SECTION_GAP_MM;
  }

  return addCanvasSlicedPages(pdf, canvas, contentW, cursorY > MARGIN_MM + 2 ? MARGIN_MM : cursorY);
}

async function captureReportSections(reportElement, pdf, contentW) {
  const sections = reportElement.querySelectorAll("[data-pdf-section]");
  let cursorY = MARGIN_MM;

  if (sections.length === 0) {
    const canvas = await captureElement(reportElement, 2);
    await appendCanvasToPdf(pdf, canvas, contentW, cursorY);
    return;
  }

  for (const section of sections) {
    const isAppendix = section.hasAttribute("data-pdf-appendix");
    const scale = isAppendix ? 1.8 : 2;
    const canvas = await captureElement(section, scale);
    cursorY = await appendCanvasToPdf(pdf, canvas, contentW, cursorY);
    const pageH = pdf.internal.pageSize.getHeight();
    if (cursorY > pageH - MARGIN_MM - 8) {
      pdf.addPage();
      cursorY = MARGIN_MM;
    }
  }
}

/**
 * Export structured test report PDF (text sections + optional appendix charts in same DOM tree).
 * @param {{ reportElement: HTMLElement, filename?: string }} opts
 */
export async function generateEvalReportPdf(opts) {
  const reportElement =
    typeof opts === "object" && opts !== null && "reportElement" in opts
      ? opts.reportElement
      : opts;
  const filename =
    (typeof opts === "object" && opts?.filename) || "eval-report.pdf";

  if (!reportElement) throw new Error("缺少报告 DOM 节点");

  const stack = reportElement.closest(".eval-report-pdf-stack");
  const pdf = new jsPDF("p", "mm", "a4");
  const pageW = pdf.internal.pageSize.getWidth();
  const contentW = pageW - MARGIN_MM * 2;

  await withCaptureEnvironment(stack, async () => {
    await captureReportSections(reportElement, pdf, contentW);
  });

  pdf.save(filename);
}
