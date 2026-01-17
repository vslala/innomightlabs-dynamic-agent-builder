import * as React from "react";
import { cn } from "../../lib/utils";

type GridCols = 1 | 2 | 3 | 4 | 5 | 6 | 12;

interface GridProps extends React.HTMLAttributes<HTMLDivElement> {
  cols?: GridCols;
  colsSm?: GridCols;
  colsMd?: GridCols;
  colsLg?: GridCols;
  colsXl?: GridCols;
  gap?: "none" | "sm" | "md" | "lg" | "xl";
  children: React.ReactNode;
}

const gapValues: Record<string, string> = {
  none: "0",
  sm: "1rem",
  md: "1.5rem",
  lg: "2rem",
  xl: "2.5rem",
};

export const Grid = React.forwardRef<HTMLDivElement, GridProps>(
  (
    {
      className,
      cols = 1,
      colsSm,
      colsLg,
      gap = "md",
      children,
      style,
      ...props
    },
    ref
  ) => {
    const gridStyle: React.CSSProperties = {
      display: "grid",
      gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
      gap: gapValues[gap],
      ...style,
    };

    return (
      <div
        ref={ref}
        className={cn("responsive-grid", className)}
        style={gridStyle}
        data-cols={cols}
        data-cols-sm={colsSm}
        data-cols-lg={colsLg}
        {...props}
      >
        {children}
      </div>
    );
  }
);
Grid.displayName = "Grid";

interface StackProps extends React.HTMLAttributes<HTMLDivElement> {
  gap?: "none" | "xs" | "sm" | "md" | "lg" | "xl";
  children: React.ReactNode;
}

const stackGapValues: Record<string, string> = {
  none: "0",
  xs: "0.5rem",
  sm: "1rem",
  md: "1.5rem",
  lg: "2rem",
  xl: "2.5rem",
};

export const Stack = React.forwardRef<HTMLDivElement, StackProps>(
  ({ className, gap = "md", children, style, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn("", className)}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: stackGapValues[gap],
          ...style,
        }}
        {...props}
      >
        {children}
      </div>
    );
  }
);
Stack.displayName = "Stack";

interface CenterProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export const Center = React.forwardRef<HTMLDivElement, CenterProps>(
  ({ className, children, style, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn("", className)}
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          ...style,
        }}
        {...props}
      >
        {children}
      </div>
    );
  }
);
Center.displayName = "Center";
