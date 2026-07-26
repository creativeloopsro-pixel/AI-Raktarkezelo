const EAN_13_LENGTH = 13;
const EAN_8_LENGTH = 8;

export type EanFormat = "EAN_13" | "EAN_8";

export function normalizeEan(value: string): string {
  return value.replace(/\D/g, "").slice(0, EAN_13_LENGTH);
}

export function getEanFormat(code: string): EanFormat | null {
  if (code.length === EAN_13_LENGTH && /^\d+$/.test(code)) return "EAN_13";
  if (code.length === EAN_8_LENGTH && /^\d+$/.test(code)) return "EAN_8";
  return null;
}

export function calculateEanCheckDigit(payload: string): number | null {
  if (!/^\d+$/.test(payload) || ![7, 12].includes(payload.length)) return null;

  const isEan13 = payload.length === 12;
  const sum = [...payload].reduce((total, digit, index) => {
    const weight = isEan13
      ? index % 2 === 0
        ? 1
        : 3
      : index % 2 === 0
        ? 3
        : 1;
    return total + Number(digit) * weight;
  }, 0);
  return (10 - (sum % 10)) % 10;
}

export function isValidEan(code: string): boolean {
  const format = getEanFormat(code);
  if (!format) return false;
  const expected = calculateEanCheckDigit(code.slice(0, -1));
  return expected === Number(code.at(-1));
}

export function getEanValidationMessage(code: string): string | null {
  if (!code) return "Az elsődleges EAN-kód megadása kötelező.";
  if (!getEanFormat(code)) {
    return "Az EAN-kód 8 vagy 13 számjegyből állhat.";
  }
  if (!isValidEan(code)) {
    return "Az EAN-kód ellenőrző számjegye hibás.";
  }
  return null;
}
