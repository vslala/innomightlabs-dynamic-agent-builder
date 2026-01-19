#!/bin/bash
# AWS Bedrock Cost Breakdown Script
# Usage: ./aws-cost-breakdown.sh [days] [profile]
# Example: ./aws-cost-breakdown.sh 30 searchexpert

DAYS=${1:-30}
PROFILE=${2:-searchexpert}
REGION="eu-west-2"

# Calculate date range
if [[ "$OSTYPE" == "darwin"* ]]; then
    START_DATE=$(date -v-${DAYS}d +%Y-%m-%d)
else
    START_DATE=$(date -d "-${DAYS} days" +%Y-%m-%d)
fi
END_DATE=$(date +%Y-%m-%d)

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║           AWS COST BREAKDOWN - Last ${DAYS} Days                      ║"
echo "║           Period: ${START_DATE} to ${END_DATE}                      ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# Get Bedrock costs by usage type
echo "📊 BEDROCK COSTS BY MODEL"
echo "─────────────────────────────────────────────────────────────────────"
printf "%-45s %12s %s\n" "MODEL" "COST" "SOURCE"
echo "─────────────────────────────────────────────────────────────────────"

aws ce get-cost-and-usage \
    --time-period Start=${START_DATE},End=${END_DATE} \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --filter '{"Dimensions": {"Key": "SERVICE", "Values": ["Amazon Bedrock Service"]}}' \
    --group-by Type=DIMENSION,Key=USAGE_TYPE \
    --profile ${PROFILE} \
    --region ${REGION} \
    --output json 2>/dev/null | jq -r '
    [.ResultsByTime[].Groups[]] |
    group_by(.Keys[0] | gsub("-(input|output)-tokens.*"; "")) |
    map({
        model: .[0].Keys[0] | gsub("-(input|output)-tokens.*"; ""),
        cost: (map(.Metrics.UnblendedCost.Amount | tonumber) | add)
    }) |
    sort_by(-.cost) |
    .[] |
    "\(.model)|\(.cost)"
' | while IFS='|' read -r model cost; do
    # Determine source based on region prefix
    if [[ "$model" == EUW2-* ]]; then
        source="🤖 Lambda"
    elif [[ "$model" == *-Titan* ]] || [[ "$model" == *-embed* ]]; then
        source="🤖 Lambda (KB)"
    else
        source="🖥️  Claude Code"
    fi

    # Format cost
    cost_fmt=$(printf "$%.2f" "$cost")

    # Clean up model name
    model_clean=$(echo "$model" | sed 's/^USE1-//; s/^EUW2-//; s/-cross-region-global//')

    printf "%-45s %12s %s\n" "$model_clean" "$cost_fmt" "$source"
done

echo "─────────────────────────────────────────────────────────────────────"

# Calculate totals
echo ""
echo "📈 SUMMARY BY SOURCE"
echo "─────────────────────────────────────────────────────────────────────"

aws ce get-cost-and-usage \
    --time-period Start=${START_DATE},End=${END_DATE} \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --filter '{"Dimensions": {"Key": "SERVICE", "Values": ["Amazon Bedrock Service"]}}' \
    --group-by Type=DIMENSION,Key=USAGE_TYPE \
    --profile ${PROFILE} \
    --region ${REGION} \
    --output json 2>/dev/null | jq -r '
    [.ResultsByTime[].Groups[]] |
    {
        lambda_euw2: (map(select(.Keys[0] | startswith("EUW2-"))) | map(.Metrics.UnblendedCost.Amount | tonumber) | add // 0),
        lambda_embed: (map(select(.Keys[0] | test("Titan|embed"; "i"))) | map(.Metrics.UnblendedCost.Amount | tonumber) | add // 0),
        total: (map(.Metrics.UnblendedCost.Amount | tonumber) | add // 0)
    } |
    "LAMBDA_EUW2=\(.lambda_euw2)\nLAMBDA_EMBED=\(.lambda_embed)\nTOTAL=\(.total)"
' | while IFS= read -r line; do
    eval "$line"
done

# Get values for summary
read LAMBDA_EUW2 LAMBDA_EMBED TOTAL < <(aws ce get-cost-and-usage \
    --time-period Start=${START_DATE},End=${END_DATE} \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --filter '{"Dimensions": {"Key": "SERVICE", "Values": ["Amazon Bedrock Service"]}}' \
    --group-by Type=DIMENSION,Key=USAGE_TYPE \
    --profile ${PROFILE} \
    --region ${REGION} \
    --output json 2>/dev/null | jq -r '
    [.ResultsByTime[].Groups[]] |
    {
        lambda_euw2: (map(select(.Keys[0] | startswith("EUW2-"))) | map(.Metrics.UnblendedCost.Amount | tonumber) | add // 0),
        lambda_embed: (map(select(.Keys[0] | test("Titan|embed"; "i"))) | map(.Metrics.UnblendedCost.Amount | tonumber) | add // 0),
        total: (map(.Metrics.UnblendedCost.Amount | tonumber) | add // 0)
    } |
    "\(.lambda_euw2) \(.lambda_embed) \(.total)"
')

LAMBDA_TOTAL=$(echo "$LAMBDA_EUW2 + $LAMBDA_EMBED" | bc)
CLAUDE_CODE=$(echo "$TOTAL - $LAMBDA_TOTAL" | bc)

printf "%-45s %12s\n" "🤖 Your Lambda (eu-west-2)" "$(printf '$%.2f' $LAMBDA_EUW2)"
printf "%-45s %12s\n" "🤖 Your Lambda (Embeddings)" "$(printf '$%.2f' $LAMBDA_EMBED)"
printf "%-45s %12s\n" "🖥️  Claude Code (us-east-1)" "$(printf '$%.2f' $CLAUDE_CODE)"
echo "─────────────────────────────────────────────────────────────────────"
printf "%-45s %12s\n" "TOTAL BEDROCK" "$(printf '$%.2f' $TOTAL)"

echo ""
echo "📋 OTHER AWS SERVICES"
echo "─────────────────────────────────────────────────────────────────────"
printf "%-45s %12s\n" "SERVICE" "COST"
echo "─────────────────────────────────────────────────────────────────────"

aws ce get-cost-and-usage \
    --time-period Start=${START_DATE},End=${END_DATE} \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --group-by Type=DIMENSION,Key=SERVICE \
    --profile ${PROFILE} \
    --region ${REGION} \
    --output json 2>/dev/null | jq -r '
    [.ResultsByTime[].Groups[]] |
    group_by(.Keys[0]) |
    map({service: .[0].Keys[0], cost: (map(.Metrics.UnblendedCost.Amount | tonumber) | add)}) |
    sort_by(-.cost) |
    .[] |
    select(.cost > 0.01) |
    "\(.service)|\(.cost)"
' | while IFS='|' read -r service cost; do
    printf "%-45s %12s\n" "$service" "$(printf '$%.2f' $cost)"
done

echo "─────────────────────────────────────────────────────────────────────"

# Total account cost
ACCOUNT_TOTAL=$(aws ce get-cost-and-usage \
    --time-period Start=${START_DATE},End=${END_DATE} \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --profile ${PROFILE} \
    --region ${REGION} \
    --output json 2>/dev/null | jq -r '
    [.ResultsByTime[].Total.UnblendedCost.Amount | tonumber] | add
')

echo ""
printf "%-45s %12s\n" "💰 TOTAL ACCOUNT COST" "$(printf '$%.2f' $ACCOUNT_TOTAL)"
echo ""
