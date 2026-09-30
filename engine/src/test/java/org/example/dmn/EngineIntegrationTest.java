package org.example.dmn;

import com.fasterxml.jackson.databind.JsonNode;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;

class EngineIntegrationTest {
    private static Main service;
    private static String xml;
    private static final String TOKEN="test-only-token-not-for-production";
    private static final HttpClient CLIENT=HttpClient.newHttpClient();

    @BeforeAll static void start() throws Exception {
        xml=Files.readString(Path.of("../examples/eligibility.dmn"));
        service=new Main("127.0.0.1",0,TOKEN);
        service.start();
    }
    @AfterAll static void stop() { service.close(); }
    private HttpResponse<String> send(String path,String method,String body,String token,String type) throws Exception {
        var builder=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+service.port()+path))
            .method(method,body==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofString(body));
        if(token!=null) builder.header("Authorization","Bearer "+token);
        if(type!=null) builder.header("Content-Type",type);
        return CLIENT.send(builder.build(),HttpResponse.BodyHandlers.ofString());
    }
    private HttpResponse<String> evaluate(String model,String decision,Object facts) throws Exception {
        return send("/evaluate","POST",Evaluator.JSON.writeValueAsString(Map.of("model_xml",model,"decision_id",decision,"facts",facts)),TOKEN,"application/json");
    }
    private JsonNode json(HttpResponse<String> response) throws Exception { return Evaluator.JSON.readTree(response.body()); }
    private void error(HttpResponse<String> response,int status,String code) throws Exception {
        assertEquals(status,response.statusCode(),response.body());
        assertEquals(code,json(response).at("/error/code").asText(),response.body());
        assertFalse(response.body().contains("java.lang"));
        assertFalse(response.body().contains("org.kie"));
        assertFalse(response.body().contains("risk_score"));
    }
    @Test void authenticatesHealth() throws Exception {
        error(send("/health","GET",null,null,null),401,"UNAUTHORIZED");
        error(send("/health","GET",null,"wrong",null),401,"UNAUTHORIZED");
        error(send("/evaluate","POST","{}",null,"application/json"),401,"UNAUTHORIZED");
        var r=send("/health","GET",null,TOKEN,null);
        assertEquals(200,r.statusCode());
        assertEquals("10.2.0",json(r).get("version").asText());
    }
    @Test void evaluatesRealUniqueDecisionTableAndHash() throws Exception {
        var r=evaluate(xml,"eligibility",Map.of("age",32,"risk_score",25));
        assertEquals(200,r.statusCode(),r.body());
        assertEquals("matched",json(r).get("status").asText());
        assertTrue(json(r).at("/result/eligible").asBoolean());
        assertEquals("low_risk_adult",json(r).at("/result/reason").asText());
        assertEquals("rule_eligible",json(r).at("/matched_rule_ids/0").asText());
        assertEquals(64,json(r).get("model_version").asText().length());
        var again=evaluate(xml,"eligibility",Map.of("age",15,"risk_score",25));
        assertEquals(json(r).get("model_version"),json(again).get("model_version"));
        assertEquals("under_age",json(again).at("/result/reason").asText());
    }
    @Test void deterministicMissingAndNullFacts() throws Exception {
        error(evaluate(xml,"eligibility",Map.of("age",32)),422,"MISSING_FACTS");
        var facts=new HashMap<String,Object>(); facts.put("age",null); facts.put("risk_score",25);
        error(evaluate(xml,"eligibility",facts),422,"MISSING_FACTS");
    }
    @Test void noMatchIsNotAnError() throws Exception {
        var r=evaluate(xml,"eligibility",Map.of("age",32,"risk_score",101));
        assertEquals(200,r.statusCode(),r.body());
        assertEquals("no_match",json(r).get("status").asText());
        assertTrue(json(r).get("result").isNull(),r.body());
        assertEquals(0,json(r).get("matched_rule_ids").size());
    }
    @Test void uniqueOverlapFailsInTheRealEngine() throws Exception {
        var overlapping=xml.replace("[0..60)","[0..100]");
        error(evaluate(overlapping,"eligibility",Map.of("age",32,"risk_score",75)),422,"EVALUATION_ERROR");
    }
    @Test void firstHitPolicyAndCollectUseEngineSemantics() throws Exception {
        var overlap=xml.replace("[0..60)","[0..100]");
        var first=evaluate(overlap.replace("hitPolicy=\"UNIQUE\"","hitPolicy=\"FIRST\""),"eligibility",Map.of("age",32,"risk_score",75));
        assertEquals(200,first.statusCode(),first.body());
        assertTrue(json(first).at("/result/eligible").asBoolean());
        // Matches are all matching rows, selected output follows FIRST.
        assertEquals(2,json(first).get("matched_rule_ids").size());
        var collect=evaluate(overlap.replace("hitPolicy=\"UNIQUE\"","hitPolicy=\"COLLECT\""),"eligibility",Map.of("age",32,"risk_score",75));
        assertEquals(200,collect.statusCode(),collect.body());
        assertTrue(json(collect).get("result").isArray());
        assertEquals(2,json(collect).get("result").size());
    }
    @Test void rejectsWrongInputType() throws Exception {
        error(evaluate(xml,"eligibility",Map.of("age","thirty","risk_score",25)),422,"EVALUATION_ERROR");
    }
    @Test void rejectsMalformedXmlAndUnknownDecision() throws Exception {
        error(evaluate("<definitions>","eligibility",Map.of()),400,"INVALID_XML");
        error(evaluate(xml,"absent",Map.of("age",32,"risk_score",25)),404,"UNKNOWN_DECISION");
    }
    @Test void rejectsDtdAndEntityExpansion() throws Exception {
        String unsafe="<!DOCTYPE definitions [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>"+xml.substring(xml.indexOf("<definitions"));
        error(evaluate(unsafe,"eligibility",Map.of()),422,"UNSAFE_MODEL");
    }
    @Test void rejectsImportsExternalHrefScriptsAndExternalFunctions() throws Exception {
        error(evaluate(xml.replace("<inputData id=\"input_age\"","<import name=\"remote\" namespace=\"urn:remote\" locationURI=\"https://example.invalid/model.dmn\" importType=\"x\"/><inputData id=\"input_age\""),"eligibility",Map.of()),422,"UNSAFE_MODEL");
        error(evaluate(xml.replace("href=\"#input_age\"","href=\"https://example.invalid/x#input_age\""),"eligibility",Map.of()),422,"UNSAFE_MODEL");
        error(evaluate(xml.replace("<text>age</text>","<text>function(x) external {java: {class: \"java.lang.System\", method signature: \"getenv()\"}}</text>"),"eligibility",Map.of()),422,"UNSAFE_MODEL");
        error(evaluate(xml.replace("<text>age</text>","<text expressionLanguage=\"javascript\">age</text>"),"eligibility",Map.of()),422,"UNSAFE_MODEL");
        error(evaluate(xml.replace("<decisionTable", "<extensionElements><script>boom</script></extensionElements><decisionTable"),"eligibility",Map.of()),422,"UNSAFE_MODEL");
    }
    @Test void acceptsDmn14AndRealFeelLiteralExpression() throws Exception {
        String literal="""
            <definitions xmlns="https://www.omg.org/spec/DMN/20211108/MODEL/" id="math" name="Math" namespace="urn:example:math">
              <inputData id="i" name="amount"><variable name="amount" typeRef="number"/></inputData>
              <decision id="d" name="Computed"><variable name="Computed" typeRef="number"/>
                <informationRequirement><requiredInput href="#i"/></informationRequirement>
                <literalExpression><text>sum(for n in [1, 2, 3] return n * amount)</text></literalExpression>
              </decision>
            </definitions>
            """;
        var r=evaluate(literal,"d",Map.of("amount",5));
        assertEquals(200,r.statusCode(),r.body());
        assertEquals(30,json(r).get("result").asInt());
        assertEquals("matched",json(r).get("status").asText());
        assertEquals(0,json(r).get("matched_rule_ids").size());
    }
    @Test void preservesExactDecimalArithmeticAndSerialization() throws Exception {
        String model="""
            <definitions xmlns="https://www.omg.org/spec/DMN/20211108/MODEL/" id="decimals" name="Decimals" namespace="urn:example:decimals">
              <inputData id="i" name="amount"><variable name="amount" typeRef="number"/></inputData>
              <decision id="d" name="Computed"><variable name="Computed"/>
                <informationRequirement><requiredInput href="#i"/></informationRequirement>
                <literalExpression><text>{exact: amount = 0.1234567890123456789012345678901234, original: amount}</text></literalExpression>
              </decision>
            </definitions>
            """;
        var decimal=new java.math.BigDecimal("0.1234567890123456789012345678901234");
        var r=evaluate(model,"d",Map.of("amount",decimal));
        assertEquals(200,r.statusCode(),r.body());
        assertTrue(json(r).at("/result/exact").asBoolean(),r.body());
        assertEquals(decimal,json(r).at("/result/original").decimalValue());
        assertTrue(r.body().contains(decimal.toPlainString()),r.body());
        // Transport can preserve more digits, but FEEL arithmetic/literals use Decimal128.
        var longer=new java.math.BigDecimal("0.123456789012345678901234567890123456789");
        var roundTrip=evaluate(model,"d",Map.of("amount",longer));
        assertEquals(200,roundTrip.statusCode(),roundTrip.body());
        assertEquals(longer,json(roundTrip).at("/result/original").decimalValue());
    }
    @Test void rejectsPathologicalNumberExponentsAndLongTokens() throws Exception {
        String prefix="{\"model_xml\":"+Evaluator.JSON.writeValueAsString(xml)+",\"decision_id\":\"eligibility\",\"facts\":{\"age\":32,\"risk_score\":";
        for(String numeric:List.of("1e10001","1e-10001","0.0000e10001","99e10000"))
            error(send("/evaluate","POST",prefix+numeric+"}}",TOKEN,"application/json"),400,"INVALID_NUMBER");
        error(send("/evaluate","POST",prefix+"1".repeat(257)+"}}",TOKEN,"application/json"),400,"INVALID_JSON");
    }
    @Test void rejectsInvalidJsonShapesAndMethods() throws Exception {
        error(send("/evaluate","POST","{",TOKEN,"application/json"),400,"INVALID_JSON");
        error(send("/evaluate","POST","{}",TOKEN,"application/json"),400,"INVALID_REQUEST");
        error(send("/evaluate","POST","{}",TOKEN,"text/plain"),415,"UNSUPPORTED_MEDIA_TYPE");
        error(send("/evaluate","GET",null,TOKEN,null),405,"METHOD_NOT_ALLOWED");
        error(send("/absent","GET",null,TOKEN,null),404,"NOT_FOUND");
        error(send("/evaluate","POST","{\"facts\":{},\"facts\":{}}",TOKEN,"application/json"),400,"INVALID_JSON");
        error(send("/evaluate","POST","{} {}",TOKEN,"application/json"),400,"INVALID_JSON");
    }
    @Test void rejectsSizeAndDepthLimits() throws Exception {
        error(evaluate(xml+" ".repeat(XmlPolicy.MAX_XML_BYTES),"eligibility",Map.of()),413,"MODEL_TOO_LARGE");
        error(evaluate(xml,"eligibility",Map.of("large","x".repeat(Evaluator.MAX_FACTS_BYTES))),413,"FACTS_TOO_LARGE");
        Object nested="x"; for(int i=0;i<34;i++) nested=Map.of("nested",nested);
        error(evaluate(xml,"eligibility",nested),413,"FACTS_TOO_COMPLEX");
        error(send("/evaluate","POST"," ".repeat(Main.MAX_REQUEST_BYTES+1),TOKEN,"application/json"),413,"REQUEST_TOO_LARGE");
    }
}
