// Copy this file into a test-only directory of official plugin-daemon 0.5.1.
// These tests import the real parser, validator, package decoder and wire types.
package dmncompat

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	pe "github.com/langgenius/dify-plugin-daemon/pkg/entities/plugin_entities"
	te "github.com/langgenius/dify-plugin-daemon/pkg/entities/tool_entities"
	"github.com/langgenius/dify-plugin-daemon/pkg/plugin_packager/decoder"
	"github.com/langgenius/dify-plugin-daemon/pkg/utils/parser"
	"github.com/langgenius/dify-plugin-daemon/pkg/validators"
)

var outputNames = map[string]bool{"result": true, "result_json": true, "matched": true,
	"outputs": true, "evaluations": true, "matched_rule_ids": true, "status": true,
	"table_id": true, "table_version": true}

func read(t *testing.T, path string) []byte {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func checkManifest(t *testing.T, manifest pe.PluginDeclaration) {
	t.Helper()
	if manifest.Version != "0.2.0" || manifest.Author != "liangquanzhou" || manifest.Name != "dmn_decision" {
		t.Fatal("wrong release identity", manifest)
	}
	if manifest.Meta.MinimumDifyVersion == nil || *manifest.Meta.MinimumDifyVersion != "1.11.1" || manifest.Meta.Runner.Version != "3.12" {
		t.Fatal("wrong Dify/Python compatibility declaration")
	}
	if err := validators.GlobalEntitiesValidator.Struct(manifest); err != nil {
		t.Fatal(err)
	}
}

func checkProvider(t *testing.T, provider pe.ToolProviderDeclaration) {
	t.Helper()
	if err := validators.GlobalEntitiesValidator.Struct(provider); err != nil {
		t.Fatal(err)
	}
	if len(provider.CredentialsSchema) != 0 || len(provider.Tools) != 1 || provider.Identity.Name != "dmn" || provider.Identity.Author != "liangquanzhou" {
		t.Fatal("provider must be credential-free with one evaluate Tool", provider)
	}
	tool := provider.Tools[0]
	if tool.Identity.Name != "evaluate" || tool.Identity.Author != "liangquanzhou" || len(tool.Parameters) != 2 {
		t.Fatal("tool identity/parameters changed", tool)
	}
	forms := map[string]pe.ToolParameterForm{}
	for _, parameter := range tool.Parameters {
		forms[parameter.Name] = parameter.Form
		if !parameter.Required || parameter.Type != pe.TOOL_PARAMETER_TYPE_STRING {
			t.Fatal(parameter)
		}
	}
	if forms["table_json"] != pe.TOOL_PARAMETER_FORM_FORM || forms["values_json"] != pe.TOOL_PARAMETER_FORM_LLM {
		t.Fatal(forms)
	}
	properties, ok := tool.OutputSchema["properties"].(map[string]interface{})
	if !ok || len(properties) != len(outputNames) {
		t.Fatal(tool.OutputSchema)
	}
	for name := range outputNames {
		if _, ok := properties[name]; !ok {
			t.Fatal("missing output", name)
		}
	}
	// Arbitrary raw JSON array values, including null elements, are intentional.
	outputs, ok := properties["outputs"].(map[string]interface{})
	if !ok || outputs["type"] != "array" {
		t.Fatal(properties["outputs"])
	}
	if items, exists := outputs["items"]; exists {
		itemMap, ok := items.(map[string]interface{})
		if !ok || len(itemMap) != 0 {
			t.Fatal("raw outputs array must not claim a homogeneous element type", items)
		}
	}
}

func TestDMNReleasePackage(t *testing.T) {
	path := os.Getenv("DMN_PACKAGE")
	if path == "" {
		t.Skip("DMN_PACKAGE not specified; final package decoder verification not run")
	}
	packageData := read(t, path)
	packageDecoder, err := decoder.NewZipPluginDecoder(packageData)
	if err != nil {
		t.Fatal(err)
	}
	defer packageDecoder.Close()
	manifest, err := packageDecoder.Manifest()
	if err != nil {
		t.Fatal(err)
	}
	checkManifest(t, manifest)
	if manifest.Tool == nil {
		t.Fatal("no Tool provider in package")
	}
	checkProvider(t, *manifest.Tool)
	// Export the actual decoded release provider for final API-model validation.
	if out := os.Getenv("DMN_PACKAGE_DECLARATION_OUTPUT"); out != "" {
		data, err := json.Marshal(manifest.Tool)
		if err != nil {
			t.Fatal(err)
		}
		if err = os.WriteFile(out, data, 0600); err != nil {
			t.Fatal(err)
		}
	}
	if err := packageDecoder.CheckAssetsValid(); err != nil {
		t.Fatal(err)
	}
	// Decoder acceptance is not trusted installation/signature verification.
	if packageDecoder.Verified() {
		t.Fatal("expected unsigned release; verification status changed")
	}
	for _, forbidden := range []string{"client.py", "engine", "frontend"} {
		if _, err := packageDecoder.Stat(forbidden); err == nil {
			t.Fatal("legacy engine/client unexpectedly included", forbidden)
		}
	}
	evidence := loadEvidence(t)
	digest := sha256.Sum256(packageData)
	if evidence.Compatibility.PackageSHA256 != hex.EncodeToString(digest[:]) {
		t.Fatal("stdio evidence must come from this exact final .difypkg, not a stale source tree")
	}
}

func TestDMNDeclarations(t *testing.T) {
	root := os.Getenv("DMN_PLUGIN_ROOT")
	if root == "" {
		t.Fatal("DMN_PLUGIN_ROOT must name the actual plugin directory")
	}
	manifest, err := parser.UnmarshalYamlBytes[pe.PluginDeclaration](read(t, filepath.Join(root, "manifest.yaml")), *validators.GlobalEntitiesValidator)
	if err != nil {
		t.Fatal(err)
	}
	checkManifest(t, manifest)
	provider, err := parser.UnmarshalYamlBytes[pe.ToolProviderDeclaration](read(t, filepath.Join(root, "provider/dmn.yaml")))
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range provider.ToolFiles {
		tool, err := parser.UnmarshalYamlBytes[pe.ToolDeclaration](read(t, filepath.Join(root, name)), *validators.GlobalEntitiesValidator)
		if err != nil {
			t.Fatal(err)
		}
		provider.Tools = append(provider.Tools, tool)
	}
	checkProvider(t, provider)
	if out := os.Getenv("DMN_DECLARATION_OUTPUT"); out != "" {
		data, err := json.Marshal(provider)
		if err != nil {
			t.Fatal(err)
		}
		if err = os.WriteFile(out, data, 0600); err != nil {
			t.Fatal(err)
		}
	}
}

type wireEvidence struct {
	Manifest      json.RawMessage   `json:"manifest"`
	Events        []json.RawMessage `json:"events"`
	Compatibility struct {
		PluginVersion     string   `json:"plugin_version"`
		SDKVersion        string   `json:"sdk_version"`
		PackageSHA256     string   `json:"package_sha256"`
		SuccessSessions   []string `json:"success_sessions"`
		ErrorSessions     []string `json:"error_sessions"`
		CredentialSession string   `json:"credential_session"`
	} `json:"compatibility"`
}

func loadEvidence(t *testing.T) wireEvidence {
	t.Helper()
	path := os.Getenv("DMN_STDIO_EVIDENCE")
	if path == "" {
		t.Fatal("DMN_STDIO_EVIDENCE must name fresh stdio_smoke.py output")
	}
	var evidence wireEvidence
	if err := json.Unmarshal(read(t, path), &evidence); err != nil {
		t.Fatal(err)
	}
	if evidence.Compatibility.PluginVersion != "0.2.0" || evidence.Compatibility.SDKVersion != "0.10.2" {
		t.Fatal("wrong evidence runtime")
	}
	return evidence
}

func TestDMNSDKStdioWire(t *testing.T) {
	evidence := loadEvidence(t)
	manifest, err := parser.UnmarshalJsonBytes[pe.PluginDeclaration](evidence.Manifest)
	if err != nil {
		t.Fatal(err)
	}
	checkManifest(t, manifest)
	successful := map[string]bool{}
	failed := map[string]bool{}
	for _, id := range evidence.Compatibility.SuccessSessions {
		successful[id] = true
	}
	for _, id := range evidence.Compatibility.ErrorSessions {
		failed[id] = true
	}
	if len(successful) != 6 || len(failed) != 18 || evidence.Compatibility.CredentialSession != "credential-empty" {
		t.Fatal("test case count changed")
	}
	variableCount, jsonCount, credentialOK, errorCount, ends := 0, 0, 0, 0, 0
	seenVariables := map[string]map[string]bool{}
	seenJSON, seenErrors, seenEnds := map[string]int{}, map[string]int{}, map[string]int{}
	for _, raw := range evidence.Events {
		event, err := parser.UnmarshalJsonBytes[pe.PluginUniversalEvent](raw)
		if err != nil {
			t.Fatal(err)
		}
		if event.Event != pe.PLUGIN_EVENT_SESSION {
			continue
		}
		if !successful[event.SessionId] && !failed[event.SessionId] && event.SessionId != "credential-empty" {
			t.Fatal("unexpected session", event.SessionId)
		}
		session, err := parser.UnmarshalJsonBytes[pe.SessionMessage](event.Data)
		if err != nil {
			t.Fatal(err)
		}
		switch session.Type {
		case pe.SESSION_MESSAGE_TYPE_END:
			ends++
			seenEnds[event.SessionId]++
		case pe.SESSION_MESSAGE_TYPE_ERROR:
			message, err := parser.UnmarshalJsonBytes[pe.ErrorResponse](session.Data)
			if err != nil {
				t.Fatal(err)
			}
			if !failed[event.SessionId] || message.ErrorType != "TableInvocationError" || message.Message == "" || strings.Contains(message.Message, "PRIVATE-VALUE-FOR-ERROR") {
				t.Fatal(event.SessionId, message)
			}
			errorCount++
			seenErrors[event.SessionId]++
		case pe.SESSION_MESSAGE_TYPE_STREAM:
			if event.SessionId == "credential-empty" {
				message, err := parser.UnmarshalJsonBytes[te.ValidateCredentialsResult](session.Data)
				if err != nil || !message.Result {
					t.Fatal(message, err)
				}
				credentialOK++
				continue
			}
			if !successful[event.SessionId] {
				t.Fatal("invalid input must not emit success/no_match", event.SessionId)
			}
			chunk, err := parser.UnmarshalJsonBytes[te.ToolResponseChunk](session.Data)
			if err != nil {
				t.Fatal(err)
			}
			switch chunk.Type {
			case te.ToolResponseChunkTypeVariable:
				name, ok := chunk.Message["variable_name"].(string)
				if !ok || !outputNames[name] || chunk.Message["variable_value"] == nil {
					t.Fatal(chunk)
				}
				if seenVariables[event.SessionId] == nil {
					seenVariables[event.SessionId] = map[string]bool{}
				}
				if seenVariables[event.SessionId][name] {
					t.Fatal("duplicate output", event.SessionId, name)
				}
				seenVariables[event.SessionId][name] = true
				variableCount++
			case te.ToolResponseChunkTypeJson:
				jsonCount++
				seenJSON[event.SessionId]++
			default:
				t.Fatal(chunk)
			}
		default:
			t.Fatal(session)
		}
	}
	for id := range successful {
		if len(seenVariables[id]) != 9 || seenJSON[id] != 1 || seenEnds[id] != 1 {
			t.Fatal("incomplete successful session", id)
		}
	}
	for id := range failed {
		if seenErrors[id] != 1 || seenEnds[id] != 1 {
			t.Fatal("incomplete failed session", id)
		}
	}
	if seenEnds["credential-empty"] != 1 || variableCount != 54 || jsonCount != 6 || credentialOK != 1 || errorCount != 18 || ends != 25 {
		t.Fatalf("unexpected counts: variables=%d json=%d credentials=%d errors=%d ends=%d", variableCount, jsonCount, credentialOK, errorCount, ends)
	}
}
