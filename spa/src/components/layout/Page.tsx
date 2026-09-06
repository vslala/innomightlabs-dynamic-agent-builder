import * as React from "react";
import { cn } from "../../lib/utils";
import styles from "./Page.module.css";

export function Page({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(styles.page, className)}
      style={{ display: "flex", flexDirection: "column", gap: "var(--page-gap)", ...style }}
      {...props}
    />
  );
}

export function PageHeader({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(styles.pageHeader, className)}
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: "var(--space-5)",
        ...style,
      }}
      {...props}
    />
  );
}

export function PageTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h1
      className={cn(styles.pageTitle, className)}
      {...props}
    />
  );
}

export function PageDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn(styles.pageDescription, className)}
      {...props}
    />
  );
}

export function PageActions({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(styles.pageActions, className)}
      style={{ gap: "var(--space-3)", ...style }}
      {...props}
    />
  );
}

export function PageBody({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(styles.pageBody, className)}
      style={{ display: "flex", flexDirection: "column", gap: "var(--section-gap)", ...style }}
      {...props}
    />
  );
}
