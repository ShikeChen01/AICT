export const truncateOutput = (text: string, maxBytes: number): string => {
  const buffer = Buffer.from(text, "utf8");
  if (buffer.byteLength <= maxBytes) {
    return text;
  }

  const headBytes = Math.floor(maxBytes * 0.6);
  const tailBytes = maxBytes - headBytes;
  const head = buffer.subarray(0, headBytes).toString("utf8");
  const tail = buffer.subarray(buffer.byteLength - tailBytes).toString("utf8");

  return `${head}\n...truncated...\n${tail}`;
};
