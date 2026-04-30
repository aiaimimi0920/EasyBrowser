package provider

import "github.com/aiaimimi0920/EasyBrowser/internal/model"

type Contract interface {
	DescribeCapabilities() model.CapabilityView
	ValidateRequest(request model.ExecuteRequest) error
	PrepareRuntime(request model.ExecuteRequest, allocation model.RuntimeAllocationView) error
	Execute(request model.ExecuteRequest, runtime model.RuntimeView) (model.ProviderExecutionResult, error)
	NormalizeError(err error) model.NormalizedError
	CollectHealth(runtime model.RuntimeView) model.RuntimeHealthView
}
