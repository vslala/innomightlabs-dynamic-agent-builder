# Payments Module Review - Production Readiness

## Overview
Comprehensive review of the payments and rate limiting system before production launch.

---

## ✅ What Works Correctly

### 1. **Billing Period Validation** (Recently Added)
**Location:** `subscriptions/repository.py:43-76`

```python
def get_active_for_user(self, user_email: str) -> Optional[Subscription]:
    # Filters by status AND checks if period has expired
    active = [
        s for s in subscriptions
        if (s.status or "").lower() in active_statuses and not _is_subscription_expired(s)
    ]
```

**What it does:**
- Checks subscription status (`active`, `trialing`, `past_due`)
- **Validates `current_period_end` hasn't passed**
- Returns `None` if expired → user falls back to `free` tier

**Edge cases handled:**
✅ Handles both Unix timestamp (from Stripe) and ISO format
✅ Handles missing/null `current_period_end` (returns `False`, doesn't block)
✅ Handles timezone-naive dates (adds UTC)

---

### 2. **Stripe Webhook Flow**
**Location:** `stripe/router.py:223-327`

**Events handled:**
1. `checkout.session.completed` - Creates subscription
2. `customer.subscription.updated` - Updates subscription
3. `customer.subscription.deleted` - Marks as deleted

**What works:**
✅ Creates user if doesn't exist
✅ Stores subscription with metadata (`plan_key`, `billing_cycle`)
✅ Updates `current_period_end` from Stripe

---

### 3. **Rate Limiting Logic**
**Location:** `rate_limits/service.py`

**Flow:**
1. Get user tier (`get_user_tier`)
2. Get tier limits from config
3. Compare current usage vs limits
4. Raise 429 if exceeded

**What works:**
✅ 0 means unlimited (enterprise tier)
✅ Defaults to `free` tier if no subscription
✅ Returns clear error messages with upgrade path

---

## ⚠️ EDGE CASES IDENTIFIED

### **Critical Edge Cases**

#### 1. **User Has Multiple Subscriptions**
**Scenario:** User subscribes twice (e.g., changes plans mid-billing)

**Current behavior:**
```python
active.sort(key=lambda s: s.updated_at or s.created_at or "", reverse=True)
return active[0]  # Returns most recently updated
```

**Status:** ✅ HANDLED
- Returns most recent active subscription
- Stripe typically cancels old one, but we handle multiples safely

---

#### 2. **Subscription Status: `past_due`**
**Scenario:** User's payment fails, subscription enters `past_due`

**Current behavior:**
```python
active_statuses = {"active", "trialing", "past_due"}
```

**Status:** ✅ HANDLED
- User retains access during `past_due` period (grace period)
- Stripe will eventually move to `unpaid` or `canceled`
- When that happens, `get_active_for_user` returns `None` → falls back to `free`

**Question:** Should `past_due` users have access?
- **Recommended:** Yes (current behavior is correct - gives grace period)

---

#### 3. **Subscription Canceled at Period End**
**Scenario:** User cancels but has access until end of billing period

**Stripe behavior:**
- Subscription remains `active` with `cancel_at_period_end: true`
- Status changes to `canceled` AFTER period ends

**Current behavior:**
- ✅ User retains access (subscription still `active`)
- ✅ After period end, `_is_subscription_expired` returns `True`
- ✅ Falls back to `free` tier

**Status:** ✅ HANDLED CORRECTLY

---

#### 4. **Checkout Session Abandoned**
**Scenario:** User starts checkout but doesn't complete payment

**Current behavior:**
- No webhook fired
- No subscription created
- User stays on `free` tier

**Status:** ✅ HANDLED (no-op)

---

#### 5. **Webhook Arrives Out of Order**
**Scenario:** `subscription.updated` arrives before `checkout.session.completed`

**Current behavior:**
```python
repo.upsert(subscription)  # Always updates by pk+sk
```

**Status:** ✅ HANDLED
- Uses `upsert` (not `create`)
- Latest data always wins
- DynamoDB single-table design prevents conflicts

---

#### 6. **Duplicate Webhooks** (Stripe Retry)
**Scenario:** Stripe retries webhook due to timeout

**Current behavior:**
```python
repo.upsert(subscription)  # Idempotent
_ensure_user_exists(email, customer_id)  # Idempotent
```

**Status:** ✅ HANDLED
- Operations are idempotent
- Safe to replay

---

#### 7. **User Downgrades Mid-Month**
**Scenario:** User on `pro` downgrades to `starter`

**Stripe behavior:**
- Immediately updates subscription
- Pro-rates credit for unused time
- Sends `subscription.updated` webhook

**Current behavior:**
- ✅ Webhook updates `plan_name` and `current_period_end`
- ✅ Rate limiter immediately enforces new (lower) limits
- ✅ User might lose access to resources (e.g., has 5 agents, new limit is 3)

**Status:** ⚠️ **NEEDS HANDLING IN UI**

**Recommendation:**
- Show warning before downgrade: "You have 5 agents but Starter allows 3. Please delete 2 agents first."
- Or: Allow existing resources but block new ones until under limit

---

#### 8. **Subscription Status: `unpaid`**
**Scenario:** Payment fails repeatedly, enters `unpaid` status

**Current behavior:**
```python
active_statuses = {"active", "trialing", "past_due"}
# "unpaid" not in list
```

**Status:** ✅ HANDLED
- `unpaid` subscriptions return `None`
- User falls back to `free` tier

---

#### 9. **Free Plan "Subscription"**
**Scenario:** User on free plan (no Stripe subscription)

**Current behavior:**
```python
if not subscription or not subscription.plan_name:
    return "free"
```

**Status:** ✅ HANDLED
- Defaults to `free` tier
- Rate limits enforced from `pricing_config.json`

---

#### 10. **Timezone Issues with `current_period_end`**
**Scenario:** Server in UTC, Stripe returns UTC timestamps

**Current behavior:**
```python
def _parse_period_end(value: Optional[str]) -> Optional[datetime]:
    if value.isdigit():
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    # ... handles ISO with/without timezone
```

**Status:** ✅ HANDLED
- Always converts to UTC
- Comparisons done in UTC

---

### **Minor Edge Cases**

#### 11. **Missing `customer_email` in Webhook**
**Current:**
```python
if not customer_email:
    log.warning(f"No email for customer {customer_id}")
    return {"status": "ignored"}
```

**Status:** ✅ HANDLED (logs and skips)

---

#### 12. **Invalid JSON in Webhook**
**Current:**
```python
except json.JSONDecodeError:
    raise HTTPException(status_code=400, detail="Invalid JSON")
```

**Status:** ✅ HANDLED

---

#### 13. **Stripe API Failure During Webhook Processing**
**Current:**
```python
async with httpx.AsyncClient() as client:
    response = await client.get(...)
    customer = response.json()  # ❌ No status check
```

**Status:** ⚠️ **MISSING ERROR HANDLING**

**Issue:** If Stripe API returns 500, `response.json()` succeeds but data is incomplete

**Fix Needed:**
```python
if response.status_code >= 400:
    log.error(f"Stripe API error: {response.status_code}")
    return {"status": "retry"}  # Let Stripe retry
customer = response.json()
```

---

#### 14. **Rate Limit Checked BEFORE Message is Saved**
**Current:** Middleware checks limit → Route saves message

**Potential race condition:**
1. User A sends message (90/100)
2. User B sends message (90/100)
3. Both pass check (90 < 100)
4. Both increment counter
5. Counter now at 92 (should be 91)

**Probability:** Very low (requires concurrent requests)

**Status:** ⚠️ **ACCEPTABLE RISK** (extremely rare, small impact)

---

## 📋 ASSUMPTIONS DOCUMENTED

### Assumption 1: Stripe Webhook Secret is Set
**Code:** `router.py:113-115`
```python
if not settings.stripe_secret_key:
    raise HTTPException(status_code=500, detail="Stripe is not configured")
```

**Assumption:** `STRIPE_SECRET_KEY` env var is set in production

---

### Assumption 2: One Active Subscription Per User
**Code:** `repository.py:43-55`

**Assumption:** While we handle multiple subscriptions, we assume **only one is active** at a time.

**Stripe reality:** User can only have one active subscription per product in Stripe's data model.

---

### Assumption 3: Free Tier Always Exists
**Code:** `service.py:24-36`
```python
def get_user_tier(self, user_email: str) -> str:
    if not subscription or not subscription.plan_name:
        return "free"  # Assumes "free" tier exists in pricing_config.json
```

**Assumption:** `pricing_config.json` always has a tier with `key: "free"`

---

### Assumption 4: Unix Timestamps are in Seconds (Not Milliseconds)
**Code:** `repository.py:68-69`
```python
if value.isdigit():
    return datetime.fromtimestamp(int(value), tz=timezone.utc)
```

**Assumption:** Stripe returns timestamps in seconds (this is correct per Stripe docs)

---

### Assumption 5: Usage Resets Monthly
**Code:** `service.py:87`
```python
period_key = datetime.now(timezone.utc).strftime("%Y-%m")
```

**Assumption:** All usage resets on calendar month boundaries (not subscription anniversary)

**Note:** This is a design choice, not a bug.

---

### Assumption 6: DynamoDB Table Exists
**Code:** Throughout

**Assumption:** `DYNAMODB_TABLE` env var points to valid table

---

### Assumption 7: Pricing Config Hasn't Changed
**Code:** `pricing_config.py:44-48`
```python
@lru_cache(maxsize=1)
def get_pricing_config() -> PricingConfig:
```

**Assumption:** Pricing config is cached and doesn't change during runtime

**Note:** Requires server restart to pick up pricing changes.

---

## 🔧 FIXES NEEDED BEFORE PRODUCTION

### **Fix 1: Add Stripe API Error Handling in Webhooks**

**File:** `stripe/router.py:259-266` and `295-302`
**Status:** ✅ Addressed in code (`_stripe_get` now checks response status)

**Current:**
```python
async with httpx.AsyncClient() as client:
    response = await client.get(...)
    stripe_sub = response.json()
```

**Fix:**
```python
async with httpx.AsyncClient() as client:
    response = await client.get(...)
    if response.status_code >= 400:
        log.error(f"Stripe API error {response.status_code}: {response.text}")
        raise HTTPException(status_code=500, detail="Stripe API error")
    stripe_sub = response.json()
```

---

### **Fix 2: Add Webhook Signature Verification**

**Status:** ✅ Addressed in code (`_verify_webhook_signature` now enforced)

**File:** `stripe/router.py:223`

**Add:**
```python
import hmac
import hashlib

def _verify_webhook_signature(payload: bytes, signature: str) -> None:
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    expected = hmac.new(
        settings.stripe_webhook_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

@router.post("/webhook")
async def handle_webhook(request: Request):
    _require_stripe_config()

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")

    _verify_webhook_signature(payload, signature)  # ADD THIS

    try:
        event = json.loads(payload.decode("utf-8"))
```

---

### **Fix 3: Handle Downgrade Edge Case in UI**

**Add to SPA:** Warning when downgrading with over-limit resources

**Example:** Before downgrade from Pro (10 agents) to Starter (3 agents):
```
⚠️ Warning: You have 7 agents. Starter plan allows 3 agents.
Please delete 4 agents before downgrading.

[Cancel] [Continue Anyway]
```

---

## ✅ PRODUCTION CHECKLIST

### Environment Variables
- [ ] `STRIPE_SECRET_KEY` set
- [ ] `STRIPE_WEBHOOK_SECRET` set
- [ ] `FRONTEND_URL` set to production URL
- [ ] `DYNAMODB_TABLE` set

### Stripe Configuration
- [ ] Production API keys in use (not test keys)
- [ ] Webhook endpoint registered: `https://api.innomightlabs.com/payments/stripe/webhook`
- [ ] Webhook events enabled:
  - [ ] `checkout.session.completed`
  - [ ] `customer.subscription.updated`
  - [ ] `customer.subscription.deleted`
- [ ] Pricing product IDs in `pricing_config.json` match production Stripe products

### Testing
- [ ] Test free tier limits
- [ ] Test upgrade flow (free → starter)
- [ ] Test downgrade flow (starter → free)
- [ ] Test subscription expiration (manually set `current_period_end` to past date)
- [ ] Test webhook replay (verify idempotency)
- [ ] Test failed payment (set test card to decline)

### Monitoring
- [ ] Set up alerts for webhook failures
- [ ] Monitor for 429 responses (rate limit hits)
- [ ] Track subscription churn (status changes to `canceled`)

---

## 🎯 RECOMMENDATIONS

### 1. Add Subscription Status Endpoint
**Add to API:**
```python
@router.get("/subscription/status")
async def get_subscription_status(user: User = Depends(get_current_user)):
    service = RateLimitService()
    return service.get_usage_summary(user.email)
```

**Response:**
```json
{
  "tier": "starter",
  "period": "2026-01",
  "limits": { "agents": 3, "messages_per_month": 2000 },
  "usage": { "agents": 2, "messages": 150 }
}
```

---

### 2. Add Billing Portal Link
**For users to manage subscription:**
```python
@router.post("/create-portal-session")
async def create_billing_portal(user: User = Depends(get_current_user)):
    subscription = subscription_repo.get_active_for_user(user.email)
    if not subscription or not subscription.customer_id:
        raise HTTPException(404, "No active subscription")

    session = await _stripe_post(
        "/billing_portal/sessions",
        {"customer": subscription.customer_id, "return_url": f"{settings.frontend_url}/dashboard/settings"}
    )
    return {"url": session["url"]}
```

---

### 3. Graceful Degradation for Expired Subscriptions

**In SPA:** Show banner when subscription expired:
```tsx
{isSubscriptionExpired && (
  <Banner variant="warning">
    Your subscription ended. You're now on the Free plan.
    <Link to="/pricing">Upgrade</Link>
  </Banner>
)}
```

---

## 📊 SUMMARY

| Category | Status |
|----------|--------|
| **Core Logic** | ✅ Sound |
| **Billing Period Check** | ✅ Working |
| **Edge Cases** | ✅ Most handled |
| **Missing Validations** | ⚠️ 2 critical (webhook signature, API error handling) |
| **Production Ready** | ⚠️ After fixes applied |

---

## 🚀 GO/NO-GO DECISION

**RECOMMENDATION:** **GO** after applying **Fix 1** and **Fix 2**

**Priority:**
1. **CRITICAL (MUST FIX):** Webhook signature verification
2. **CRITICAL (MUST FIX):** Stripe API error handling
3. **HIGH (SHOULD FIX):** Downgrade UI warning
4. **MEDIUM (NICE TO HAVE):** Subscription status endpoint
5. **LOW (FUTURE):** Billing portal

**Estimated time to production-ready:** 1-2 hours
