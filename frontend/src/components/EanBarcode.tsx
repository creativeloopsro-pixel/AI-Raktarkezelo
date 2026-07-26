import { memo, useMemo } from "react";
import { Barcode } from "lucide-react";

import {
  getEanFormat,
  isValidEan,
  type EanFormat
} from "../lib/ean";

type Props = {
  code?: string | null;
  compact?: boolean;
};

const LEFT_PATTERNS = [
  "0001101",
  "0011001",
  "0010011",
  "0111101",
  "0100011",
  "0110001",
  "0101111",
  "0111011",
  "0110111",
  "0001011"
];

const G_PATTERNS = [
  "0100111",
  "0110011",
  "0011011",
  "0100001",
  "0011101",
  "0111001",
  "0000101",
  "0010001",
  "0001001",
  "0010111"
];

const RIGHT_PATTERNS = [
  "1110010",
  "1100110",
  "1101100",
  "1000010",
  "1011100",
  "1001110",
  "1010000",
  "1000100",
  "1001000",
  "1110100"
];

const EAN_13_PARITY = [
  "LLLLLL",
  "LLGLGG",
  "LLGGLG",
  "LLGGGL",
  "LGLLGG",
  "LGGLLG",
  "LGGGLL",
  "LGLGLG",
  "LGLGGL",
  "LGGLGL"
];

type EncodedEan = {
  bits: string;
  format: EanFormat;
  quietLeft: number;
  quietRight: number;
  guardIndexes: Set<number>;
};

function encodeEan(code: string): EncodedEan | null {
  const format = getEanFormat(code);
  if (!format) return null;

  if (format === "EAN_8") {
    const left = code
      .slice(0, 4)
      .split("")
      .map((digit) => LEFT_PATTERNS[Number(digit)])
      .join("");
    const right = code
      .slice(4)
      .split("")
      .map((digit) => RIGHT_PATTERNS[Number(digit)])
      .join("");
    return {
      bits: `101${left}01010${right}101`,
      format,
      quietLeft: 7,
      quietRight: 7,
      guardIndexes: new Set([0, 1, 2, 31, 32, 33, 34, 35, 64, 65, 66])
    };
  }

  const parity = EAN_13_PARITY[Number(code[0])];
  const left = code
    .slice(1, 7)
    .split("")
    .map((digit, index) =>
      parity[index] === "G"
        ? G_PATTERNS[Number(digit)]
        : LEFT_PATTERNS[Number(digit)]
    )
    .join("");
  const right = code
    .slice(7)
    .split("")
    .map((digit) => RIGHT_PATTERNS[Number(digit)])
    .join("");
  return {
    bits: `101${left}01010${right}101`,
    format,
    quietLeft: 11,
    quietRight: 7,
    guardIndexes: new Set([0, 1, 2, 45, 46, 47, 48, 49, 92, 93, 94])
  };
}

function EanBarcode({ code, compact = false }: Props) {
  const encoded = useMemo(() => (code ? encodeEan(code) : null), [code]);

  if (!code || !encoded) {
    return (
      <span className={`ean-empty ${compact ? "compact" : ""}`}>
        <Barcode aria-hidden="true" />
        Nincs elsődleges EAN
      </span>
    );
  }

  const { bits, format, quietLeft, quietRight, guardIndexes } = encoded;
  const width = bits.length + quietLeft + quietRight;
  const start = quietLeft;
  const valid = isValidEan(code);
  const leftDigits = format === "EAN_13" ? code.slice(1, 7) : code.slice(0, 4);
  const rightDigits = format === "EAN_13" ? code.slice(7) : code.slice(4);
  const leftGroupStart = start + 3;
  const rightGroupStart =
    start + 3 + (format === "EAN_13" ? 42 : 28) + 5;

  return (
    <figure
      className={`ean-barcode ${compact ? "compact" : ""} ${valid ? "" : "invalid"}`}
      title={valid ? `EAN-kód: ${code}` : "Az EAN ellenőrző számjegye hibás."}
    >
      <svg
        viewBox={`0 0 ${width} 58`}
        role="img"
        aria-label={`Vizuális ${format.replace("_", "-")} vonalkód: ${code}`}
        preserveAspectRatio="xMidYMid meet"
        shapeRendering="crispEdges"
      >
        <rect width={width} height="58" fill="#fff" />
        {[...bits].map((bit, index) =>
          bit === "1" ? (
            <rect
              key={index}
              x={start + index}
              y="3"
              width="1"
              height={guardIndexes.has(index) ? 43 : 38}
              fill="#071521"
            />
          ) : null
        )}
        {format === "EAN_13" ? (
          <text
            x={quietLeft - 4}
            y="55"
            textAnchor="middle"
            className="ean-svg-number"
          >
            {code[0]}
          </text>
        ) : null}
        {[...leftDigits].map((digit, index) => (
          <text
            key={`left-${index}`}
            x={leftGroupStart + index * 7 + 3.5}
            y="55"
            textAnchor="middle"
            className="ean-svg-number"
          >
            {digit}
          </text>
        ))}
        {[...rightDigits].map((digit, index) => (
          <text
            key={`right-${index}`}
            x={rightGroupStart + index * 7 + 3.5}
            y="55"
            textAnchor="middle"
            className="ean-svg-number"
          >
            {digit}
          </text>
        ))}
      </svg>
      <figcaption>
        <span>EAN</span>
        <code>{code}</code>
        {!valid ? <small>Ellenőrizendő</small> : null}
      </figcaption>
    </figure>
  );
}

export default memo(EanBarcode);
