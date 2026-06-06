/** Chinese chapter numerals for PDF / narrative report sections. */
export const CN_SECTION_NUMS = [
  "一",
  "二",
  "三",
  "四",
  "五",
  "六",
  "七",
  "八",
  "九",
  "十",
];

export function cnSectionNum(index) {
  return CN_SECTION_NUMS[index] ?? String(index + 1);
}

export function cnSubSectionNum(sectionIndex, subIndex) {
  return `${sectionIndex + 1}.${subIndex}`;
}
