package org.example.dmn;

import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.regex.Pattern;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.*;
import org.xml.sax.InputSource;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

/** Admission policy only. All decision and FEEL semantics are implemented by Apache KIE. */
final class XmlPolicy {
    static final int MAX_XML_BYTES = 512 * 1024;
    private static final Set<String> MODEL_NAMESPACES = Set.of(
        "https://www.omg.org/spec/DMN/20191111/MODEL/", // DMN 1.3
        "https://www.omg.org/spec/DMN/20211108/MODEL/"); // DMN 1.4
    private static final Set<String> FEEL_LANGUAGES = Set.of(
        "FEEL", "https://www.omg.org/spec/DMN/20191111/FEEL/",
        "https://www.omg.org/spec/DMN/20211108/FEEL/",
        "http://www.omg.org/spec/FEEL/20140401");
    // Deliberately conservative: even "external" inside a string is rejected.
    private static final Pattern EXTERNAL = Pattern.compile("(?i)\\bexternal\\b");

    static void validate(String xml) {
        if (xml.getBytes(StandardCharsets.UTF_8).length > MAX_XML_BYTES)
            throw new ServiceError(413, "MODEL_TOO_LARGE", "DMN XML exceeds the size limit.");
        if (xml.contains("<!DOCTYPE") || xml.contains("<!ENTITY")) unsafe();
        try {
            var f = DocumentBuilderFactory.newInstance();
            f.setNamespaceAware(true);
            f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
            f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            f.setFeature("http://xml.org/sax/features/external-general-entities", false);
            f.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            f.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
            f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            f.setXIncludeAware(false);
            f.setExpandEntityReferences(false);
            var builder = f.newDocumentBuilder();
            builder.setErrorHandler(new DefaultHandler() {
                @Override public void error(SAXParseException e) throws SAXParseException { throw e; }
                @Override public void fatalError(SAXParseException e) throws SAXParseException { throw e; }
            });
            var document = builder.parse(new InputSource(new StringReader(xml)));
            var root = document.getDocumentElement();
            if (!"definitions".equals(root.getLocalName()) || !MODEL_NAMESPACES.contains(root.getNamespaceURI()))
                throw new ServiceError(422, "UNSUPPORTED_MODEL", "Use a single DMN 1.3 or 1.4 model.");
            inspect(document, 0, new int[]{0});
        } catch (ServiceError e) { throw e; }
        catch (Exception e) { throw new ServiceError(400, "INVALID_XML", "DMN XML is malformed or disallowed."); }
    }

    private static void inspect(Node node, int depth, int[] elements) {
        if (depth > 64 || ++elements[0] > 10000)
            throw new ServiceError(413, "MODEL_TOO_COMPLEX", "DMN XML exceeds structural limits.");
        if (node.getNodeType() == Node.PROCESSING_INSTRUCTION_NODE) unsafe();
        if (node instanceof Element e) {
            String local = e.getLocalName();
            if (Set.of("import", "script", "scriptTask", "externalFunction").contains(local)) unsafe();
            if ("extensionElements".equals(local) && e.getChildNodes().getLength() > 0) {
                // No executable vendor extensions; whitespace-only containers are harmless.
                for (Node c=e.getFirstChild(); c!=null; c=c.getNextSibling())
                    if (c instanceof Element) unsafe();
            }
            for (int i=0; i<e.getAttributes().getLength(); i++) {
                Node attr=e.getAttributes().item(i);
                String name=attr.getLocalName();
                String value=attr.getNodeValue();
                if ("expressionLanguage".equals(name) && !value.isBlank() && !FEEL_LANGUAGES.contains(value)) unsafe();
                if ("typeLanguage".equals(name) && !value.isBlank() && !FEEL_LANGUAGES.contains(value)) unsafe();
                if ("kind".equals(name) && "functionDefinition".equals(local) && !"FEEL".equals(value)) unsafe();
                if ("href".equals(name) && !value.startsWith("#")) unsafe();
            }
            if ("text".equals(local) && EXTERNAL.matcher(e.getTextContent()).find()) unsafe();
            if ("http://www.w3.org/2001/XInclude".equals(e.getNamespaceURI())) unsafe();
        }
        for (Node child=node.getFirstChild(); child!=null; child=child.getNextSibling())
            inspect(child, depth+1, elements);
    }
    private static void unsafe() {
        throw new ServiceError(422, "UNSAFE_MODEL", "External references, scripts, entities, and extensions are not allowed.");
    }
}
