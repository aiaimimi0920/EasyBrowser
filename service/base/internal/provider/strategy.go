package provider

import "strings"

const (
	StrategyProfileBalanced         = "balanced"
	StrategyProfileLocalFirst       = "local-first"
	StrategyProfileRemoteFirst      = "remote-first"
	StrategyProfileLatencyFirst     = "latency-first"
	StrategyProfileStabilityFirst   = "stability-first"
	StrategyProfileCostAware        = "cost-aware"
	StrategyProfileStealthFirst     = "stealth-first"
	StrategyProfileChromeFirst      = "chrome-first"
	StrategyProfileCamoufoxFirst    = "camoufox-first"
	StrategyProfileBrowserbaseFirst = "browserbase-first"
)

type StrategyScoreInput struct {
	Profile        string
	ProviderID     string
	Action         string
	ResourceKind   string
	RuntimeReuse   string
	ReadyRuntimes  int
	RecentFailures int
	TotalFailures  int
}

type StrategyScoreBreakdown struct {
	BaseScore            int
	ProfileBonus         int
	ReuseBonus           int
	ReadyRuntimeBonus    int
	RecentFailurePenalty int
	TotalFailurePenalty  int
}

type StrategyScoreResult struct {
	Score     int
	Breakdown StrategyScoreBreakdown
}

func NormalizeStrategyProfile(profile string) string {
	switch strings.ToLower(strings.TrimSpace(profile)) {
	case "", "default", "balanced", "auto":
		return StrategyProfileBalanced
	case "local", "local-first", "local_first":
		return StrategyProfileLocalFirst
	case "remote", "remote-first", "remote_first":
		return StrategyProfileRemoteFirst
	case "latency", "latency-first", "latency_first":
		return StrategyProfileLatencyFirst
	case "stability", "stability-first", "stability_first":
		return StrategyProfileStabilityFirst
	case "cost", "cost-aware", "cost_aware", "local-cheap":
		return StrategyProfileCostAware
	case "stealth", "stealth-first", "stealth_first":
		return StrategyProfileStealthFirst
	case "chrome", "chrome-first", "chrome_first":
		return StrategyProfileChromeFirst
	case "camoufox", "camoufox-first", "camoufox_first":
		return StrategyProfileCamoufoxFirst
	case "browserbase", "browserbase-first", "browserbase_first":
		return StrategyProfileBrowserbaseFirst
	default:
		return strings.ToLower(strings.TrimSpace(profile))
	}
}

func StrategyPriority(profile, providerID, action, resourceKind string) int {
	profile = NormalizeStrategyProfile(profile)
	providerID = strings.ToLower(strings.TrimSpace(providerID))
	resourceKind = CanonicalResourceKind(resourceKind)

	switch profile {
	case StrategyProfileLocalFirst:
		if isLocalProvider(providerID) {
			return 0
		}
		return 1
	case StrategyProfileRemoteFirst:
		if isRemoteProvider(providerID) {
			return 0
		}
		return 1
	case StrategyProfileLatencyFirst, StrategyProfileStabilityFirst, StrategyProfileCostAware:
		return 0
	case StrategyProfileStealthFirst, StrategyProfileCamoufoxFirst:
		switch providerID {
		case "camoufox":
			return 0
		case "geekez":
			return 1
		case "chrome":
			return 2
		case "browserbase":
			if resourceKind == "session" || ClassifyAction(action) == ActionClassSession {
				return 0
			}
			return 3
		default:
			return 4
		}
	case StrategyProfileChromeFirst:
		switch providerID {
		case "chrome":
			return 0
		case "camoufox":
			return 1
		case "geekez":
			return 2
		case "browserbase":
			if resourceKind == "session" || ClassifyAction(action) == ActionClassSession {
				return 0
			}
			return 3
		default:
			return 4
		}
	case StrategyProfileBrowserbaseFirst:
		if providerID == "browserbase" {
			return 0
		}
		if isLocalProvider(providerID) {
			return 1
		}
		return 2
	case StrategyProfileBalanced:
		fallthrough
	default:
		return 0
	}
}

func StrategyScore(input StrategyScoreInput) int {
	return StrategyScoreDetailed(input).Score
}

func StrategyScoreDetailed(input StrategyScoreInput) StrategyScoreResult {
	profile := NormalizeStrategyProfile(input.Profile)
	providerID := strings.ToLower(strings.TrimSpace(input.ProviderID))
	action := CanonicalActionName(input.Action)
	resourceKind := CanonicalResourceKind(input.ResourceKind)
	runtimeReuse := normalizeRuntimeReuse(input.RuntimeReuse)

	result := StrategyScoreResult{}

	switch profile {
	case StrategyProfileBalanced:
		result.Breakdown.BaseScore += 100
	case StrategyProfileLocalFirst:
		if isLocalProvider(providerID) {
			result.Breakdown.ProfileBonus += 240
		}
	case StrategyProfileRemoteFirst:
		if isRemoteProvider(providerID) {
			result.Breakdown.ProfileBonus += 240
		}
	case StrategyProfileLatencyFirst:
		result.Breakdown.BaseScore += 110
		if isLocalProvider(providerID) && (resourceKind == "page" || ClassifyAction(action) == ActionClassPage || ClassifyAction(action) == ActionClassProvider) {
			result.Breakdown.ProfileBonus += 30
		}
		if providerID == "browserbase" && (resourceKind == "session" || ClassifyAction(action) == ActionClassSession) {
			result.Breakdown.ProfileBonus += 30
		}
	case StrategyProfileStabilityFirst:
		result.Breakdown.BaseScore += 140
	case StrategyProfileCostAware:
		if resourceKind == "session" || ClassifyAction(action) == ActionClassSession {
			if providerID == "browserbase" {
				result.Breakdown.ProfileBonus += 220
			}
		} else if isLocalProvider(providerID) {
			result.Breakdown.ProfileBonus += 220
		}
	case StrategyProfileStealthFirst, StrategyProfileCamoufoxFirst:
		switch providerID {
		case "camoufox":
			result.Breakdown.ProfileBonus += 260
		case "geekez":
			result.Breakdown.ProfileBonus += 210
		case "chrome":
			result.Breakdown.ProfileBonus += 160
		case "browserbase":
			if resourceKind == "session" || ClassifyAction(action) == ActionClassSession {
				result.Breakdown.ProfileBonus += 220
			}
		}
	case StrategyProfileChromeFirst:
		switch providerID {
		case "chrome":
			result.Breakdown.ProfileBonus += 260
		case "camoufox":
			result.Breakdown.ProfileBonus += 160
		case "geekez":
			result.Breakdown.ProfileBonus += 120
		case "browserbase":
			if resourceKind == "session" || ClassifyAction(action) == ActionClassSession {
				result.Breakdown.ProfileBonus += 220
			}
		}
	case StrategyProfileBrowserbaseFirst:
		if providerID == "browserbase" {
			result.Breakdown.ProfileBonus += 260
		} else if isLocalProvider(providerID) {
			result.Breakdown.ProfileBonus += 120
		}
	}

	switch runtimeReuse {
	case "require_reuse":
		if input.ReadyRuntimes == 0 {
			result.Breakdown.ReuseBonus -= 500
		}
		result.Breakdown.ReuseBonus += input.ReadyRuntimes * 180
	case "prefer_reuse":
		result.Breakdown.ReuseBonus += input.ReadyRuntimes * 120
	case "prefer_fresh":
		result.Breakdown.ReuseBonus += 20
		result.Breakdown.ReuseBonus -= input.ReadyRuntimes * 30
	case "require_fresh":
		result.Breakdown.ReuseBonus += 40
		result.Breakdown.ReuseBonus -= input.ReadyRuntimes * 160
	default:
		result.Breakdown.ReadyRuntimeBonus += input.ReadyRuntimes * 50
	}

	switch profile {
	case StrategyProfileLatencyFirst:
		result.Breakdown.ReadyRuntimeBonus += input.ReadyRuntimes * 80
		result.Breakdown.RecentFailurePenalty -= input.RecentFailures * 45
		result.Breakdown.TotalFailurePenalty -= input.TotalFailures * 8
	case StrategyProfileStabilityFirst:
		result.Breakdown.ReadyRuntimeBonus += input.ReadyRuntimes * 15
		result.Breakdown.RecentFailurePenalty -= input.RecentFailures * 120
		result.Breakdown.TotalFailurePenalty -= input.TotalFailures * 25
	default:
		result.Breakdown.RecentFailurePenalty -= input.RecentFailures * 70
		result.Breakdown.TotalFailurePenalty -= input.TotalFailures * 12
	}

	result.Score =
		result.Breakdown.BaseScore +
			result.Breakdown.ProfileBonus +
			result.Breakdown.ReuseBonus +
			result.Breakdown.ReadyRuntimeBonus +
			result.Breakdown.RecentFailurePenalty +
			result.Breakdown.TotalFailurePenalty

	return result
}

func normalizeRuntimeReuse(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "require_reuse", "prefer_reuse", "require_fresh", "prefer_fresh":
		return strings.ToLower(strings.TrimSpace(value))
	default:
		return ""
	}
}

func isLocalProvider(providerID string) bool {
	switch providerID {
	case "chrome", "camoufox", "geekez":
		return true
	default:
		return false
	}
}

func isRemoteProvider(providerID string) bool {
	return providerID == "browserbase"
}
