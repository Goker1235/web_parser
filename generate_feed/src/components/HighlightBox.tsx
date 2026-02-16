"use client";

import { CSSProperties } from "react";

interface Props {
  rect: DOMRect | null;
  className?: string;
}

export const HighlightBox = ({ rect, className }: Props) => {
  if (!rect) return null;

  const style: CSSProperties = {
    position: "absolute",
    top: rect.top + window.scrollY,
    left: rect.left + window.scrollX,
    width: rect.width,
    height: rect.height,
    border: "2px solid #007bff",
    backgroundColor: "rgba(0,123,255,0.1)",
    pointerEvents: "none",
    zIndex: 9999,
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "flex-start",
  };

  const labelStyle: CSSProperties = {
    position: "absolute",
    top: -20,
    left: 0,
    backgroundColor: "#007bff",
    color: "#fff",
    fontSize: 12,
    padding: "2px 6px",
    borderRadius: 3,
    pointerEvents: "none",
  };

  return (
    <div style={style}>
      {className && <div style={labelStyle}>{className}</div>}
    </div>
  );
};
