/** KG layout: spine-first swim lanes — flow column fixed; attach nodes in compact side grids. */

export const LAYOUT_NODE_W = 100;
export const LAYOUT_NODE_H = 40;
const FLOW_ROW = 76;
const ATTACH_ROW = 48;
const TRANS_ROW = 52;
const MIN_NODE_GAP = 48;
const START_Y = 64;

const COL = {
  meta: 52,
  left: 132,
  left2: 212,
  flow: 308,
  branch: 404,
  transition: 492,
  right: 584,
  right2: 676,
};

const LANE_BY_TYPE = {
  role: "meta",
  flow: "flow",
  know: "attach",
  dial: "attach",
  boun: "attach",
};

const LANE_BY_NODE_TYPE = {
  meta: "meta",
  flow_step: "flow",
  transition: "transition",
  knowledge: "attach",
  constraint: "attach",
};

const ATTACH_KIND_ORDER_LEFT = ["objection", "dialogue", "boundary", "other_left"];
const ATTACH_KIND_ORDER_RIGHT = ["knowledge", "retention", "flow_aux", "other_right"];

function bucket(node) {
  if (isBranchNode(node)) return "branch";
  const nt = String(node.node_type || "");
  if (LANE_BY_NODE_TYPE[nt]) return LANE_BY_NODE_TYPE[nt];
  const t = String(node.type || "dial");
  return LANE_BY_TYPE[t] ?? "attach";
}

function idSortKey(id) {
  const s = String(id);
  const m = s.match(/^([A-Za-z_]+)(\d+)/);
  if (m) {
    const num = Number(m[2]);
    const tail = Number.isFinite(num) ? String(num).padStart(6, "0") : String(m[2] ?? "");
    return `${m[1]}\t${tail}`;
  }
  return s;
}

function flowOrder(id) {
  const m = String(id).match(/^F(\d+)/i);
  return m ? Number(m[1]) : 9999;
}

function isFlowStepId(id) {
  return /^F\d+$/i.test(String(id)) && !String(id).includes("RETAIN");
}

function isBranchNode(node) {
  const id = String(node.id || "");
  const nt = String(node.node_type || "");
  return (
    id.startsWith("branch::") ||
    id.startsWith("op::") ||
    nt === "flow_branch" ||
    nt === "op_step" ||
    node.type === "branch"
  );
}

function branchStep(id) {
  const m = String(id).match(/^(?:branch|op)::(\d+)::/);
  return m ? Number(m[1]) : 9999;
}

function attachKind(node) {
  const id = String(node.id || "");
  const t = String(node.type || "");
  const nt = String(node.node_type || "");
  if (/^K\d/i.test(id) || t === "know" || nt === "knowledge") return "knowledge";
  if (/^D\d/i.test(id) || t === "dial") return "dialogue";
  if (/^B\d/i.test(id) || t === "boun") return "boundary";
  if (/^R\d/i.test(id) || /RETAIN/i.test(id)) return "retention";
  if (/^F/i.test(id)) return "flow_aux";
  if (/^(FAQ|OBJ)/i.test(id)) return "objection";
  return "other_left";
}

/** Ensure nodes sharing a column never overlap vertically. */
function deOverlapColumns(nodes, minGap = MIN_NODE_GAP) {
  if (!nodes.length) return nodes;
  const colKey = (x) => Math.round(Number(x || 0) / 8) * 8;
  const groups = new Map();
  for (const n of nodes) {
    const k = colKey(n.x);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(n);
  }
  for (const col of groups.values()) {
    col.sort((a, b) => a.y - b.y);
    for (let i = 1; i < col.length; i += 1) {
      const need = col[i - 1].y + minGap;
      if (col[i].y < need) col[i].y = need;
    }
  }
  return nodes;
}

/** Stack items in one or more columns without stretching the flow spine. */
function placeGrid(items, colXs, startY) {
  if (!items.length) return { placed: [], height: 0 };
  const cols = Math.max(1, colXs.length);
  const placed = [];
  items.forEach((n, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    placed.push({ ...n, x: colXs[col], y: startY + row * ATTACH_ROW });
  });
  const rows = Math.ceil(items.length / cols);
  return { placed, height: rows * ATTACH_ROW };
}

/** Vertical stack with guaranteed minimum row gap (transition / meta rails). */
function placeStack(items, colX, startY, rowStep) {
  return items.map((n, i) => ({ ...n, x: colX, y: startY + i * rowStep }));
}

function collectAttachGroups(attachNodes) {
  const groups = new Map();
  for (const n of attachNodes) {
    let kind = attachKind(n);
    if (kind === "other_left") {
      const id = String(n.id);
      if (/^K/i.test(id)) kind = "knowledge";
      else if (/^R/i.test(id)) kind = "retention";
      else kind = "other_right";
    }
    if (!groups.has(kind)) groups.set(kind, []);
    groups.get(kind).push({ ...n });
  }
  for (const [kind, list] of groups) {
    list.sort((a, b) => idSortKey(a.id).localeCompare(idSortKey(b.id)));
    groups.set(kind, list);
  }
  return groups;
}

function flattenKinds(groups, kindOrder) {
  const out = [];
  for (const kind of kindOrder) {
    const items = groups.get(kind) || [];
    if (items.length) out.push(...items);
  }
  return out;
}

/**
 * Layout (spine-first):
 * - 中列 F1–Fn：固定行距，不被侧列撑高
 * - 分支列：对齐对应 F 步骤
 * - 左/右附属：紧凑多列网格（K、D 多时自动分列）
 * - 过渡列：沿脊柱均匀分布
 */
export function layoutKgNodes(nodes) {
  if (!nodes?.length) return [];

  const buckets = { meta: [], flow: [], branch: [], transition: [], attach: [] };
  for (const n of nodes) {
    const b = bucket(n);
    if (b === "flow" && isFlowStepId(n.id)) buckets.flow.push({ ...n });
    else if (b === "flow") buckets.attach.push({ ...n });
    else buckets[b].push({ ...n });
  }

  buckets.flow.sort((a, b) => flowOrder(a.id) - flowOrder(b.id));

  const attachGroups = collectAttachGroups(buckets.attach);
  const leftItems = flattenKinds(attachGroups, ATTACH_KIND_ORDER_LEFT);
  const rightItems = flattenKinds(attachGroups, ATTACH_KIND_ORDER_RIGHT);

  const leftCols = leftItems.length > 10 ? [COL.left, COL.left2] : [COL.left];
  const rightCols = rightItems.length > 10 ? [COL.right, COL.right2] : [COL.right];

  const out = [];

  const flowTop = START_Y;
  buckets.flow.forEach((n, i) => {
    out.push({ ...n, x: COL.flow, y: flowTop + i * FLOW_ROW });
  });

  const spineTop = flowTop;
  const spineBottom = flowTop + Math.max(0, buckets.flow.length - 1) * FLOW_ROW;

  const branchesByStep = new Map();
  for (const n of buckets.branch) {
    const step = branchStep(n.id);
    if (!branchesByStep.has(step)) branchesByStep.set(step, []);
    branchesByStep.get(step).push({ ...n });
  }
  for (const [step, branchList] of branchesByStep) {
    const parent = out.find((n) => n.id === `F${step}`);
    const anchorY = parent?.y ?? flowTop + (step - 1) * FLOW_ROW;
    const sorted = [...branchList].sort((a, b) => idSortKey(a.id).localeCompare(idSortKey(b.id)));
    const spread = sorted.length > 1 ? Math.max(MIN_NODE_GAP, ATTACH_ROW) : 0;
    const startY = anchorY - ((sorted.length - 1) * spread) / 2;
    sorted.forEach((n, i) => {
      out.push({ ...n, x: COL.branch, y: startY + i * spread });
    });
  }

  const leftGrid = placeGrid(leftItems, leftCols, spineTop);
  const rightGrid = placeGrid(rightItems, rightCols, spineTop);
  out.push(...leftGrid.placed, ...rightGrid.placed);

  const metaOrder = ["GLOBAL_DIALOGUE", "GLOBAL_BOUNDARY", "START", "CLOSING", "END"];
  const metaSorted = [...buckets.meta].sort((a, b) => {
    const ia = metaOrder.indexOf(a.id);
    const ib = metaOrder.indexOf(b.id);
    if (ia >= 0 && ib >= 0) return ia - ib;
    if (ia >= 0) return -1;
    if (ib >= 0) return 1;
    return idSortKey(a.id).localeCompare(idSortKey(b.id));
  });

  const globals = metaSorted.filter((n) => !["START", "CLOSING", "END"].includes(String(n.id)));
  const startNode = metaSorted.find((n) => n.id === "START");
  const endNode = metaSorted.find((n) => n.id === "END");

  if (globals.length) {
    out.push(...placeStack(globals, COL.meta, spineTop - globals.length * TRANS_ROW - 20, TRANS_ROW));
  }
  if (startNode) {
    out.push({ ...startNode, x: COL.meta, y: spineTop - 16 });
  }
  if (endNode) {
    out.push({ ...endNode, x: COL.meta, y: spineBottom + TRANS_ROW + 16 });
  }

  const transOrder = ["OBJECTION", "FAQ_NORMAL", "FAQ_OOB", "F3_RETAIN", "OBJ_FINAL", "CLOSING"];
  const trans = [...buckets.transition].sort((a, b) => {
    const ia = transOrder.indexOf(a.id);
    const ib = transOrder.indexOf(b.id);
    if (ia >= 0 && ib >= 0) return ia - ib;
    if (ia >= 0) return -1;
    if (ib >= 0) return 1;
    return idSortKey(a.id).localeCompare(idSortKey(b.id));
  });
  out.push(...placeStack(trans, COL.transition, spineTop, TRANS_ROW));

  return deOverlapColumns(out);
}

/** @deprecated overlap pass caused diagonal chains; layout pre-allocates lanes */
export function resolveNodeOverlaps(nodes) {
  return nodes;
}

export function fitViewBox(nodes, options = {}) {
  const paddingRatio =
    typeof options === "number" ? options : (options.paddingRatio ?? 0.04);
  const aspectRatio =
    typeof options === "object" && options != null ? options.aspectRatio : null;
  const preferCompact =
    typeof options === "object" && options != null ? options.preferCompact !== false : true;

  if (!nodes?.length) {
    return { x: 0, y: 0, w: 640, h: 480 };
  }

  const padNode = 48;
  const xs = nodes.map((n) => Number(n.x || 0));
  const ys = nodes.map((n) => Number(n.y || 0));
  let minX = Math.min(...xs) - padNode;
  let maxX = Math.max(...xs) + padNode;
  let minY = Math.min(...ys) - padNode;
  let maxY = Math.max(...ys) + padNode;
  let w = Math.max(320, maxX - minX);
  let h = Math.max(260, maxY - minY);

  if (aspectRatio && aspectRatio > 0) {
    const contentAspect = w / h;
    if (preferCompact && contentAspect > Math.max(aspectRatio, 1.2)) {
      const newH = w / Math.max(aspectRatio, 1.05);
      const extra = (newH - h) / 2;
      minY -= extra;
      h = newH;
    } else if (contentAspect > aspectRatio) {
      const newH = w / aspectRatio;
      minY -= (newH - h) / 2;
      h = newH;
    } else if (contentAspect < aspectRatio * 0.85) {
      const newW = h * aspectRatio;
      minX -= (newW - w) / 2;
      w = newW;
    }
  }

  const padX = w * paddingRatio;
  const padY = h * paddingRatio;
  return {
    x: minX - padX,
    y: minY - padY,
    w: w + padX * 2,
    h: h + padY * 2,
  };
}
