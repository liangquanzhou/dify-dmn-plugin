package org.example.dmn;

import com.sun.net.httpserver.*;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import java.util.concurrent.*;

/** HTTP boundary for trusted, reviewed models. Not an arbitrary-code sandbox. */
public final class Main implements AutoCloseable {
    static final int MAX_REQUEST_BYTES=2*1024*1024;
    static final int MAX_RESPONSE_BYTES=1024*1024;
    private final HttpServer server;
    private final ExecutorService executor=Executors.newVirtualThreadPerTaskExecutor();
    private final Semaphore permits=new Semaphore(4);
    private final String token;
    private final Evaluator evaluator=new Evaluator();

    public Main(String host,int port,String token) throws IOException {
        this.token=token==null?"":token;
        this.server=HttpServer.create(new InetSocketAddress(host,port),32);
        server.createContext("/",this::handle);
        server.setExecutor(executor);
    }
    public void start() { server.start(); }
    public int port() { return server.getAddress().getPort(); }
    @Override public void close() { server.stop(0); executor.shutdownNow(); }

    private void handle(HttpExchange exchange) throws IOException {
        boolean acquired=false;
        try {
            authenticate(exchange);
            String path=exchange.getRequestURI().getPath();
            if("/health".equals(path)) {
                requireMethod(exchange,"GET");
                send(exchange,200,Map.of("status","ok","engine","Apache KIE","version","10.2.0"));
                return;
            }
            if(!"/evaluate".equals(path)) throw new ServiceError(404,"NOT_FOUND","Endpoint was not found.");
            requireMethod(exchange,"POST");
            String type=exchange.getRequestHeaders().getFirst("Content-Type");
            if(type==null || !type.split(";",2)[0].trim().equalsIgnoreCase("application/json"))
                throw new ServiceError(415,"UNSUPPORTED_MEDIA_TYPE","Use application/json.");
            if(!permits.tryAcquire()) throw new ServiceError(429,"BUSY","Engine is busy; retry later.");
            acquired=true;
            var bytes=exchange.getRequestBody().readNBytes(MAX_REQUEST_BYTES+1);
            if(bytes.length>MAX_REQUEST_BYTES) throw new ServiceError(413,"REQUEST_TOO_LARGE","Request exceeds the size limit.");
            com.fasterxml.jackson.databind.JsonNode request;
            try { request=Evaluator.parseRequest(bytes); }
            catch(ServiceError e) { throw e; }
            catch(Exception e) { throw new ServiceError(400,"INVALID_JSON","Request must contain valid JSON."); }
            send(exchange,200,evaluator.evaluate(request));
        } catch(ServiceError e) {
            if(e.status==401) exchange.getResponseHeaders().set("WWW-Authenticate","Bearer");
            if(e.status==429) exchange.getResponseHeaders().set("Retry-After","1");
            send(exchange,e.status,Map.of("error",Map.of("code",e.code,"message",e.getMessage())));
        } catch(Exception e) {
            send(exchange,500,Map.of("error",Map.of("code","INTERNAL_ERROR","message","The engine could not process the request.")));
        } finally {
            if(acquired) permits.release();
            exchange.close();
        }
    }
    private void authenticate(HttpExchange exchange) {
        if(token.isBlank()) return;
        String supplied=exchange.getRequestHeaders().getFirst("Authorization");
        if(supplied==null || !MessageDigest.isEqual(("Bearer "+token).getBytes(StandardCharsets.UTF_8),supplied.getBytes(StandardCharsets.UTF_8)))
            throw new ServiceError(401,"UNAUTHORIZED","A valid bearer token is required.");
    }
    private static void requireMethod(HttpExchange exchange,String expected) {
        if(!expected.equals(exchange.getRequestMethod())) {
            exchange.getResponseHeaders().set("Allow",expected);
            throw new ServiceError(405,"METHOD_NOT_ALLOWED","HTTP method is not allowed.");
        }
    }
    private static void send(HttpExchange exchange,int status,Object value) throws IOException {
        byte[] body=Evaluator.JSON.writeValueAsBytes(value);
        if(body.length>MAX_RESPONSE_BYTES) {
            status=422;
            body=Evaluator.JSON.writeValueAsBytes(Map.of("error",Map.of("code","RESULT_TOO_LARGE","message","Decision output exceeds the size limit.")));
        }
        exchange.getResponseHeaders().set("Content-Type","application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control","no-store");
        exchange.getResponseHeaders().set("X-Content-Type-Options","nosniff");
        exchange.sendResponseHeaders(status,body.length);
        exchange.getResponseBody().write(body);
    }
    public static void main(String[] args) throws Exception {
        String token=System.getenv().getOrDefault("DMN_API_TOKEN","");
        String environment=System.getenv().getOrDefault("DMN_ENV","production");
        if(!"development".equals(environment) && token.length()<32)
            throw new IllegalArgumentException("Production requires DMN_API_TOKEN of at least 32 characters.");
        String host=System.getenv().getOrDefault("DMN_BIND_HOST","127.0.0.1");
        int port=Integer.parseInt(System.getenv().getOrDefault("PORT","8080"));
        System.setProperty("sun.net.httpserver.maxReqTime","15");
        System.setProperty("sun.net.httpserver.maxRspTime","30");
        System.setProperty("jdk.httpserver.maxConnections","64");
        var service=new Main(host,port,token);
        Runtime.getRuntime().addShutdownHook(new Thread(service::close));
        service.start();
        System.out.println("DMN engine listening on "+host+":"+service.port()+" (Apache KIE 10.2.0)");
    }
}
