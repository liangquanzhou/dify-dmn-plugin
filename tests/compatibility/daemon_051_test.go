// Copy this file into a test-only directory of the official plugin-daemon
// 0.5.1 source tree. It imports the real parser, validator and wire types.
package dmncompat

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	pe "github.com/langgenius/dify-plugin-daemon/pkg/entities/plugin_entities"
	te "github.com/langgenius/dify-plugin-daemon/pkg/entities/tool_entities"
	"github.com/langgenius/dify-plugin-daemon/pkg/plugin_packager/decoder"
	"github.com/langgenius/dify-plugin-daemon/pkg/utils/parser"
	"github.com/langgenius/dify-plugin-daemon/pkg/validators"
)

func TestDMNReleasePackage(t *testing.T) {
	path := os.Getenv("DMN_PACKAGE")
	if path == "" {
		t.Skip("DMN_PACKAGE not specified; final package decoder verification not run")
	}
	packageDecoder, err := decoder.NewZipPluginDecoder(read(t, path))
	if err != nil {
		t.Fatal(err)
	}
	defer packageDecoder.Close()
	manifest, err := packageDecoder.Manifest()
	if err != nil {
		t.Fatal(err)
	}
	if manifest.Version != "0.1.1" || manifest.Tool == nil || len(manifest.Tool.Tools) != 1 {
		t.Fatal(manifest)
	}
	if err := validators.GlobalEntitiesValidator.Struct(manifest); err != nil {
		t.Fatal(err)
	}
	if err := packageDecoder.CheckAssetsValid(); err != nil {
		t.Fatal(err)
	}
	// This release is intentionally unsigned: never label decoder acceptance
	// as trusted installation/signature verification.
	if packageDecoder.Verified() {
		t.Fatal("expected unsigned release; verification status changed")
	}
}

func read(t *testing.T, path string) []byte {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return data
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
	if manifest.Meta.MinimumDifyVersion == nil || *manifest.Meta.MinimumDifyVersion != "1.11.1" {
		t.Fatal("wrong minimum version")
	}
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
	if err := validators.GlobalEntitiesValidator.Struct(provider); err != nil {
		t.Fatal(err)
	}
	if len(provider.CredentialsSchema) != 2 || len(provider.Tools) != 1 {
		t.Fatal("provider declarations lost")
	}
	tool := provider.Tools[0]
	forms := map[string]pe.ToolParameterForm{}
	for _, parameter := range tool.Parameters {
		forms[parameter.Name] = parameter.Form
	}
	if forms["model_xml"] != pe.TOOL_PARAMETER_FORM_FORM || forms["decision_id"] != pe.TOOL_PARAMETER_FORM_FORM || forms["facts_json"] != pe.TOOL_PARAMETER_FORM_LLM {
		t.Fatal(forms)
	}
	if len(tool.OutputSchema["properties"].(map[string]interface{})) != 5 {
		t.Fatal(tool.OutputSchema)
	}
	// Also export the daemon-normalized declaration for exact Dify 1.11.1 API validation.
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

func TestDMNSDKStdioWire(t *testing.T) {
	evidence := os.Getenv("DMN_STDIO_EVIDENCE")
	if evidence == "" {
		t.Fatal("DMN_STDIO_EVIDENCE must name fresh stdio_smoke.py output")
	}
	var recorded struct {
		Manifest json.RawMessage   `json:"manifest"`
		Events   []json.RawMessage `json:"events"`
	}
	if err := json.Unmarshal(read(t, evidence), &recorded); err != nil {
		t.Fatal(err)
	}
	if _, err := parser.UnmarshalJsonBytes[pe.PluginDeclaration](recorded.Manifest); err != nil {
		t.Fatal(err)
	}
	variableCount, jsonCount, credentialOK, credentialError, ends := 0, 0, 0, 0, 0
	for _, raw := range recorded.Events {
		event, err := parser.UnmarshalJsonBytes[pe.PluginUniversalEvent](raw)
		if err != nil {
			t.Fatal(err)
		}
		if event.Event != pe.PLUGIN_EVENT_SESSION {
			continue
		}
		session, err := parser.UnmarshalJsonBytes[pe.SessionMessage](event.Data)
		if err != nil {
			t.Fatal(err)
		}
		switch session.Type {
		case pe.SESSION_MESSAGE_TYPE_END:
			ends++
		case pe.SESSION_MESSAGE_TYPE_ERROR:
			message, err := parser.UnmarshalJsonBytes[pe.ErrorResponse](session.Data)
			if err != nil {
				t.Fatal(err)
			}
			if event.SessionId != "credential-rejected" || message.ErrorType != "ToolProviderCredentialValidationError" {
				t.Fatal(message)
			}
			credentialError++
		case pe.SESSION_MESSAGE_TYPE_STREAM:
			if event.SessionId == "credential-success" {
				message, err := parser.UnmarshalJsonBytes[te.ValidateCredentialsResult](session.Data)
				if err != nil || !message.Result {
					t.Fatal(message, err)
				}
				credentialOK++
				continue
			}
			chunk, err := parser.UnmarshalJsonBytes[te.ToolResponseChunk](session.Data)
			if err != nil {
				t.Fatal(err)
			}
			switch chunk.Type {
			case te.ToolResponseChunkTypeVariable:
				if _, ok := chunk.Message["variable_name"].(string); !ok {
					t.Fatal(chunk)
				}
				if chunk.Message["variable_value"] == nil {
					t.Fatal("top-level null not accepted by Dify API")
				}
				variableCount++
			case te.ToolResponseChunkTypeJson:
				jsonCount++
			default:
				t.Fatal(chunk)
			}
		default:
			t.Fatal(session)
		}
	}
	if variableCount != 25 || jsonCount != 5 || credentialOK != 1 || credentialError != 1 || ends != 7 {
		t.Fatalf("unexpected counts: variables=%d json=%d credentials=%d/%d ends=%d", variableCount, jsonCount, credentialOK, credentialError, ends)
	}
}
