import * as React from "react";
import { Link, type LinkProps } from "react-router-dom";
import { cn } from "../../lib/utils";
import { buttonVariants, type ButtonProps } from "./button";

type LinkButtonBaseProps = Omit<ButtonProps, "asChild" | "type"> & {
  children: React.ReactNode;
};

type InternalLinkButtonProps = LinkButtonBaseProps &
  Omit<LinkProps, "className" | "children"> & {
    href?: never;
    external?: false;
  };

type ExternalLinkButtonProps = LinkButtonBaseProps &
  Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "className" | "children"> & {
    href: string;
    to?: never;
    external: true;
  };

export type LinkButtonProps = InternalLinkButtonProps | ExternalLinkButtonProps;

const linkButtonPaddingBySize: Record<string, React.CSSProperties> = {
  sm: {
    minHeight: "2.25rem",
    paddingBlock: "0.5rem",
    paddingInline: "1rem",
  },
};

const getLinkButtonStyle = (
  size: LinkButtonProps["size"],
  style: React.CSSProperties | undefined
): React.CSSProperties | undefined => {
  const sizeStyle = size ? linkButtonPaddingBySize[size] : undefined;
  return sizeStyle ? { ...sizeStyle, ...style } : style;
};

export const LinkButton = React.forwardRef<HTMLAnchorElement, LinkButtonProps>(
  ({ className, variant, size, children, external, style, ...props }, ref) => {
    const classes = cn(buttonVariants({ variant, size, className }), "no-underline");
    const linkStyle = getLinkButtonStyle(size, style);

    if (external) {
      const { href, target = "_blank", rel, ...anchorProps } = props as ExternalLinkButtonProps;
      return (
        <a
          ref={ref}
          href={href}
          target={target}
          rel={rel ?? (target === "_blank" ? "noreferrer" : undefined)}
          className={classes}
          style={linkStyle}
          {...anchorProps}
        >
          {children}
        </a>
      );
    }

  const linkProps = props as InternalLinkButtonProps;
  return (
      <Link ref={ref} className={classes} style={linkStyle} {...linkProps}>
        {children}
      </Link>
    );
  }
);

LinkButton.displayName = "LinkButton";
