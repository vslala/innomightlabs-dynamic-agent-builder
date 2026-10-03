import { Badge } from '@/components/Badge/Badge'
import { productStatuses, type ProductStatus } from '@/content/products'

export function ProductStatusBadge({ status }: { status: ProductStatus }) {
  const { label, tone } = productStatuses[status]
  return <Badge tone={tone}>{label}</Badge>
}
