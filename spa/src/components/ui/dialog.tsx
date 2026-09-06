import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "../../lib/utils";
import styles from "./dialog.module.css";

const Dialog = DialogPrimitive.Root;
const DialogTrigger = DialogPrimitive.Trigger;
const DialogPortal = DialogPrimitive.Portal;
const DialogClose = DialogPrimitive.Close;

const DialogOverlay = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(styles.overlay, className)}
    {...props}
  />
));
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName;

const DialogContent = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, style, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(styles.content, className)}
      style={{
        padding: "var(--dialog-padding)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-6)",
        backgroundColor: "var(--surface-page)",
        opacity: 1,
        ...style,
      }}
      {...props}
    >
      {children}
      <DialogPrimitive.Close
        style={{
          position: "absolute",
          right: "1rem",
          top: "1rem",
          borderRadius: "0.25rem",
          opacity: 0.7,
          transition: "opacity 0.2s",
        }}
      >
        <X style={{ height: "1rem", width: "1rem", color: "var(--text-muted)" }} />
        <span className={styles.srOnly}>Close</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPortal>
));
DialogContent.displayName = DialogPrimitive.Content.displayName;

const DialogHeader = ({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(styles.header, className)}
    style={{
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-2)",
      textAlign: "left",
      ...style,
    }}
    {...props}
  />
);
DialogHeader.displayName = "DialogHeader";

const DialogFooter = ({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(styles.footer, className)}
    style={{
      display: "flex",
      flexDirection: "row",
      justifyContent: "flex-end",
      gap: "var(--space-3)",
      marginTop: "var(--space-2)",
      ...style,
    }}
    {...props}
  />
);
DialogFooter.displayName = "DialogFooter";

const DialogTitle = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn(styles.title, className)}
    style={{
      fontSize: "1.125rem",
      fontWeight: 600,
      lineHeight: 1.2,
      color: "var(--text-primary)",
    }}
    {...props}
  />
));
DialogTitle.displayName = DialogPrimitive.Title.displayName;

const DialogDescription = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn(styles.description, className)}
    style={{
      fontSize: "0.875rem",
      color: "var(--text-muted)",
      marginTop: "0.25rem",
    }}
    {...props}
  />
));
DialogDescription.displayName = DialogPrimitive.Description.displayName;

const DialogBody = ({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(styles.body, className)}
    style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)", ...style }}
    {...props}
  />
);
DialogBody.displayName = "DialogBody";

const DialogSection = ({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(styles.section, className)}
    style={{ padding: "var(--space-5)", ...style }}
    {...props}
  />
);
DialogSection.displayName = "DialogSection";

const DialogActions = DialogFooter;

export {
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogClose,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogBody,
  DialogSection,
  DialogActions,
  DialogTitle,
  DialogDescription,
};
