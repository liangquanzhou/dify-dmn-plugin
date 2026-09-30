package org.example.dmn;

import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.TemporalAmount;
import java.util.*;
import org.kie.dmn.api.core.*;
import org.kie.dmn.api.core.event.*;
import org.kie.dmn.core.internal.utils.DMNRuntimeBuilder;
import org.kie.internal.io.ResourceFactory;

public final class Evaluator {
    static final int MAX_FACTS_BYTES=128*1024;
    static final ObjectMapper JSON=JsonMapper.builder()
        .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();
    static {
        JSON.getFactory().setStreamReadConstraints(StreamReadConstraints.builder()
            .maxNestingDepth(64).maxStringLength(1024*1024).maxNumberLength(256).build());
    }

    static JsonNode parseRequest(byte[] bytes) throws java.io.IOException {
        // Check the original token, including its lexical exponent, before tree normalization.
        try (var parser=JSON.getFactory().createParser(bytes)) {
            JsonToken token;
            while ((token=parser.nextToken())!=null) {
                if (token==JsonToken.VALUE_NUMBER_INT || token==JsonToken.VALUE_NUMBER_FLOAT) {
                    String lexical=parser.getText();
                    if (lexical.length()>256)
                        throw new ServiceError(400,"INVALID_NUMBER","Numeric token exceeds the length limit.");
                    int e=Math.max(lexical.indexOf('e'),lexical.indexOf('E'));
                    if (e>=0 && new java.math.BigInteger(lexical.substring(e+1)).abs()
                            .compareTo(java.math.BigInteger.valueOf(10000))>0)
                        throw new ServiceError(400,"INVALID_NUMBER","Numeric exponent exceeds the allowed range.");
                    checkDecimal(new BigDecimal(lexical),400,"INVALID_NUMBER");
                }
            }
        }
        return JSON.readTree(bytes);
    }
    private static void checkDecimal(BigDecimal value,int status,String code) {
        long adjusted=(long)value.precision()-value.scale()-1;
        if (Math.abs((long)value.scale())>10000 || Math.abs(adjusted)>10000)
            throw new ServiceError(status,code,"Numeric exponent exceeds the allowed range.");
    }

    public Map<String,Object> evaluate(JsonNode request) {
        validateRequest(request);
        String xml=request.get("model_xml").textValue();
        String decisionId=request.get("decision_id").textValue();
        XmlPolicy.validate(xml);
        JsonNode facts=request.get("facts");
        try {
            if (JSON.writeValueAsBytes(facts).length > MAX_FACTS_BYTES)
                throw new ServiceError(413,"FACTS_TOO_LARGE","Facts exceed the size limit.");
        } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
            throw new ServiceError(400,"INVALID_FACTS","Facts must be JSON data.");
        }
        inspectFacts(facts,0,new int[]{0});
        try {
            // No KJAR, Maven resolution, imports, deployment, or script engine is involved.
            // Strict mode disables Drools' ExtendedDMNProfile and enables type checking.
            var resource=ResourceFactory.newByteArrayResource(xml.getBytes(StandardCharsets.UTF_8));
            resource.setSourcePath("request.dmn");
            DMNRuntime runtime=DMNRuntimeBuilder.usingStrict().fromResources(List.of(resource))
                .getOrElseThrow(e -> new ServiceError(422,"INVALID_MODEL","DMN model could not be compiled."));
            if (runtime.getModels().size()!=1)
                throw new ServiceError(422,"INVALID_MODEL","Exactly one DMN model is required.");
            DMNModel model=runtime.getModels().getFirst();
            if (model.hasErrors()) throw new ServiceError(422,"INVALID_MODEL","DMN model could not be compiled.");
            var decision=model.getDecisionById(decisionId);
            if (decision==null) throw new ServiceError(404,"UNKNOWN_DECISION","Decision ID was not found in the model.");
            for (var input:model.getRequiredInputsForDecisionId(decisionId)) {
                if (!facts.hasNonNull(input.getName()))
                    throw new ServiceError(422,"MISSING_FACTS","A declared required input is missing or null.");
            }
            var ruleIds=new LinkedHashSet<String>();
            var targetTableSeen=new boolean[]{false};
            var targetTableMatched=new boolean[]{false};
            runtime.addListener(new DMNRuntimeEventListener() {
                @Override public void afterEvaluateDecisionTable(AfterEvaluateDecisionTableEvent event) {
                    // Metadata is scoped to the requested decision, not its dependency decisions.
                    if (!decision.getName().equals(event.getDecisionName())) return;
                    targetTableSeen[0]=true;
                    if (event.getMatches()!=null && !event.getMatches().isEmpty()) targetTableMatched[0]=true;
                    if (event.getMatchesIds()!=null) for (String id:event.getMatchesIds())
                        if (id!=null && !id.isBlank()) ruleIds.add(id);
                }
            });
            DMNContext context=runtime.newContext();
            facts.fields().forEachRemaining(entry -> context.set(entry.getKey(),JSON.convertValue(entry.getValue(),Object.class)));
            DMNResult evaluated=runtime.evaluateById(model,context,decisionId);
            if (evaluated.hasErrors())
                throw new ServiceError(422,"EVALUATION_ERROR","Decision evaluation failed; check types, expressions, and hit policy.");
            var result=evaluated.getDecisionResultById(decisionId);
            if (result==null || result.getEvaluationStatus()!=DMNDecisionResult.DecisionEvaluationStatus.SUCCEEDED)
                throw new ServiceError(422,"EVALUATION_ERROR","Decision did not complete successfully.");
            Object normalized=normalize(result.getResult(),0,new int[]{0});
            boolean noMatch=targetTableSeen[0] && !targetTableMatched[0];
            var response=new LinkedHashMap<String,Object>();
            response.put("status",noMatch?"no_match":"matched");
            response.put("result",normalized);
            response.put("matched_rule_ids",List.copyOf(ruleIds));
            response.put("model_version",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(xml.getBytes(StandardCharsets.UTF_8))));
            return response;
        } catch (ServiceError e) { throw e; }
        catch (Exception e) { throw new ServiceError(422,"EVALUATION_ERROR","DMN model could not be evaluated."); }
    }

    private static void validateRequest(JsonNode n) {
        if(n==null || !n.isObject() || n.size()!=3 || !n.has("model_xml") || !n.has("decision_id") || !n.has("facts")
            || !n.get("model_xml").isTextual() || n.get("model_xml").textValue().isBlank()
            || !n.get("decision_id").isTextual() || n.get("decision_id").textValue().isBlank()
            || n.get("decision_id").textValue().length()>256 || !n.get("facts").isObject())
            throw new ServiceError(400,"INVALID_REQUEST","Provide model_xml, decision_id, and an object facts.");
    }
    private static void inspectFacts(JsonNode n,int depth,int[] count) {
        if(depth>32 || ++count[0]>10000)
            throw new ServiceError(413,"FACTS_TOO_COMPLEX","Facts exceed structural limits.");
        if(n.isNumber()) checkDecimal(n.decimalValue(),400,"INVALID_NUMBER");
        for(JsonNode child:n) inspectFacts(child,depth+1,count);
    }
    private static Object normalize(Object value,int depth,int[] count) {
        if(depth>32 || ++count[0]>10000)
            throw new ServiceError(422,"RESULT_TOO_COMPLEX","Decision output exceeds structural limits.");
        if(value instanceof BigDecimal decimal) checkDecimal(decimal,422,"UNSUPPORTED_RESULT");
        if(value==null || value instanceof String || value instanceof Boolean || value instanceof BigDecimal
            || value instanceof java.math.BigInteger || value instanceof Integer || value instanceof Long) return value;
        if(value instanceof Number n) {
            if(!Double.isFinite(n.doubleValue())) throw new ServiceError(422,"UNSUPPORTED_RESULT","Decision output is not JSON-compatible.");
            return value;
        }
        if(value instanceof Map<?,?> map) {
            Map<String,Object> result=new LinkedHashMap<>();
            for(var e:map.entrySet()) {
                if(!(e.getKey() instanceof String key)) throw new ServiceError(422,"UNSUPPORTED_RESULT","Decision output is not JSON-compatible.");
                result.put(key,normalize(e.getValue(),depth+1,count));
            }
            return result;
        }
        if(value instanceof Collection<?> collection) {
            List<Object> result=new ArrayList<>();
            for(Object entry:collection) result.add(normalize(entry,depth+1,count));
            return result;
        }
        if(value instanceof TemporalAccessor || value instanceof TemporalAmount) return value.toString();
        throw new ServiceError(422,"UNSUPPORTED_RESULT","Decision output is not JSON-compatible.");
    }
}
