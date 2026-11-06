// homedock-ui/vue3/static/js/__Islands__/sheetsCsv.ts
// Copyright © 2023-2026 Banshee, All Rights Reserved
// See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
// https://www.banshee.pro

import type { Cell, CellMatrix, Sheet } from "@fortune-sheet/core";

export type SheetFormat = "xlsx" | "csv" | "tsv";

export interface CsvLayout {
  delimiter: string;
  lineBreak: string;
  bom: boolean;
}

const DELIMITER_CANDIDATES = [",", ";", "\t", "|"];

const NUMERIC_TEXT = /^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i;

const LEADING_ZERO = /^[+-]?0\d/;

const MIN_ROWS = 84;

const MIN_COLUMNS = 60;

export function sheetFormat(fileName: string): SheetFormat {
  const extension = fileName.split(".").pop()?.toLowerCase();
  return extension === "csv" || extension === "tsv" ? extension : "xlsx";
}

function decodeText(source: ArrayBuffer): { text: string; bom: boolean } {
  const bytes = new Uint8Array(source);
  const bom = bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf;
  const body = bom ? bytes.subarray(3) : bytes;

  try {
    return { text: new TextDecoder("utf-8", { fatal: true }).decode(body), bom };
  } catch {
    return { text: new TextDecoder("windows-1252").decode(body), bom };
  }
}

function detectDelimiter(text: string): string {
  const counts = new Map(DELIMITER_CANDIDATES.map((candidate) => [candidate, 0]));
  let quoted = false;

  for (const char of text) {
    if (char === '"') quoted = !quoted;
    else if (!quoted && (char === "\n" || char === "\r")) break;
    else if (!quoted && counts.has(char)) counts.set(char, counts.get(char)! + 1);
  }

  let best = ",";
  for (const [candidate, count] of counts) {
    if (count > counts.get(best)!) best = candidate;
  }

  return best;
}

function parseDelimited(text: string, delimiter: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index++) {
    const char = text[index];

    if (quoted) {
      if (char !== '"') field += char;
      else if (text[index + 1] === '"') {
        field += '"';
        index++;
      } else quoted = false;
      continue;
    }

    if (char === '"' && field === "") quoted = true;
    else if (char === delimiter) {
      row.push(field);
      field = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[index + 1] === "\n") index++;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else field += char;
  }

  if (field !== "" || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows;
}

function cellFromText(text: string): Cell {
  if (LEADING_ZERO.test(text)) return { v: text, m: text, ct: { fa: "@", t: "s" } };
  if (NUMERIC_TEXT.test(text)) return { v: Number(text), m: text, ct: { fa: "General", t: "n" } };

  return { v: text, m: text, ct: { fa: "General", t: "g" } };
}

export function readCsv(source: ArrayBuffer, format: SheetFormat, sheetName: string): { sheets: Sheet[]; layout: CsvLayout } {
  const { text, bom } = decodeText(source);
  const delimiter = format === "tsv" ? "\t" : detectDelimiter(text);
  const lineBreak = text.includes("\r\n") ? "\r\n" : "\n";
  const rows = parseDelimited(text, delimiter);

  const celldata: Sheet["celldata"] = [];
  let columns = 0;

  rows.forEach((values, r) => {
    columns = Math.max(columns, values.length);
    values.forEach((value, c) => {
      if (value !== "") celldata.push({ r, c, v: cellFromText(value) });
    });
  });

  return {
    sheets: [{ name: sheetName, celldata, order: 0, status: 1, row: Math.max(MIN_ROWS, rows.length + 1), column: Math.max(MIN_COLUMNS, columns + 1) }],
    layout: { delimiter, lineBreak, bom },
  };
}

function cellText(cell: Cell | null | undefined): string {
  if (!cell) return "";
  if (cell.ct?.t === "inlineStr" && cell.ct.s) return cell.ct.s.map((part: { v?: string }) => part.v ?? "").join("");

  const value = cell.m ?? cell.v;
  return value === null || value === undefined ? "" : String(value);
}

function quoteField(value: string, delimiter: string): string {
  return value.includes(delimiter) || value.includes('"') || value.includes("\n") || value.includes("\r") ? `"${value.replace(/"/g, '""')}"` : value;
}

export function writeCsv(data: CellMatrix | undefined, layout: CsvLayout): Blob {
  const rows = (data ?? []).map((row) => (row ?? []).map(cellText));

  let lastRow = -1;
  let lastColumn = -1;

  rows.forEach((values, r) => {
    values.forEach((value, c) => {
      if (value === "") return;
      lastRow = r;
      lastColumn = Math.max(lastColumn, c);
    });
  });

  const lines: string[] = [];
  for (let r = 0; r <= lastRow; r++) {
    const fields: string[] = [];
    for (let c = 0; c <= lastColumn; c++) fields.push(quoteField(rows[r]?.[c] ?? "", layout.delimiter));
    lines.push(fields.join(layout.delimiter));
  }

  const body = lines.length ? lines.join(layout.lineBreak) + layout.lineBreak : "";
  return new Blob([layout.bom ? "﻿" : "", body], { type: "text/csv" });
}
