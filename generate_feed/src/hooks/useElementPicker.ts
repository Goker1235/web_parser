"use client";

import { useEffect, useState } from "react";
import { SelectedElementInfo } from "@/types/picker";

export const useElementPicker = () => {
  const [isActive, setIsActive] = useState(false);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [hoverClass, setHoverClass] = useState<string>("");
  const [selected, setSelected] = useState<SelectedElementInfo | null>(null);

  useEffect(() => {
    if (!isActive) return;

    const handleMouseOver = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target) return;

      setRect(target.getBoundingClientRect());
      setHoverClass(target.className || "-");
    };

    const handleClick = (e: MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();

      const target = e.target as HTMLElement;

      setSelected({
        tag: target.tagName.toLowerCase(),
        className: target.className || "-",
        id: target.id || "-",
      });

      setIsActive(false);
      setRect(null);
      setHoverClass("");
    };

    document.body.style.cursor = "crosshair";

    document.addEventListener("mouseover", handleMouseOver);
    document.addEventListener("click", handleClick, true);

    return () => {
      document.body.style.cursor = "default";
      document.removeEventListener("mouseover", handleMouseOver);
      document.removeEventListener("click", handleClick, true);
    };
  }, [isActive]);

  return {
    isActive,
    setIsActive,
    rect,
    hoverClass,
    selected,
  };
};
