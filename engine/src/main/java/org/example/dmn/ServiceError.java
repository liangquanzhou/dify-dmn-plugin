package org.example.dmn;

/** Only these fixed public messages leave the process; no XML, facts, or engine diagnostics. */
final class ServiceError extends RuntimeException {
    final int status;
    final String code;
    ServiceError(int status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }
}
