package com.datashark.ui.client;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import org.eclipse.core.runtime.ILog;
import org.eclipse.core.runtime.Platform;
import org.eclipse.core.runtime.Status;
import org.osgi.framework.Bundle;
import org.osgi.framework.FrameworkUtil;

/**
 * Singleton client for maintaining a persistent connection to the DataShark Python server.
 * 
 * This client manages a single Python process that runs for the lifetime of the DBeaver window.
 * It handles JSON-RPC communication over stdin/stdout and redirects stderr to the Eclipse log.
 */
public class DataSharkClient {
    
    private static final AtomicReference<DataSharkClient> INSTANCE = new AtomicReference<>();
    private static final Object LOCK = new Object();
    
    private final AtomicBoolean isRunning = new AtomicBoolean(false);
    private final AtomicBoolean isShuttingDown = new AtomicBoolean(false);
    
    private Process process;
    private OutputStream stdin;
    private Thread stdoutReaderThread;
    private Thread stderrReaderThread;
    
    private final Bundle bundle;
    private final ILog log;
    
    private int requestIdCounter = 0;
    private final Object requestIdLock = new Object();
    
    /**
     * Private constructor for singleton pattern.
     */
    private DataSharkClient() {
        bundle = FrameworkUtil.getBundle(DataSharkClient.class);
        if (bundle != null) {
            log = Platform.getLog(bundle);
        } else {
            log = null;
        }
    }
    
    /**
     * Get the singleton instance of DataSharkClient.
     * 
     * @return The singleton instance
     */
    public static DataSharkClient getInstance() {
        DataSharkClient instance = INSTANCE.get();
        if (instance == null) {
            synchronized (LOCK) {
                instance = INSTANCE.get();
                if (instance == null) {
                    instance = new DataSharkClient();
                    INSTANCE.set(instance);
                }
            }
        }
        return instance;
    }
    
    /**
     * Start the DataShark Python server process.
     * 
     * This method is idempotent - calling it multiple times will only start the process once.
     * 
     * @throws IOException if the process cannot be started
     * @throws IllegalStateException if the client is shutting down
     */
    public void start() throws IOException {
        if (isShuttingDown.get()) {
            throw new IllegalStateException("Client is shutting down");
        }
        
        if (isRunning.get()) {
            logInfo("DataShark process already running");
            return;
        }
        
        synchronized (LOCK) {
            if (isRunning.get()) {
                return;
            }
            
            logInfo("Starting DataShark Python server...");
            
            // Build command: try 'datashark serve' first, fallback to 'python3 -m datashark.cli serve'
            List<String> command = new ArrayList<>();
            command.add("datashark");
            command.add("serve");
            
            ProcessBuilder pb = new ProcessBuilder(command);
            
            // Set working directory to user's home or current directory
            // In production, this might be configurable via preferences
            pb.directory(new java.io.File(System.getProperty("user.home")));
            
            // Merge environment variables (preserve existing PATH, PYTHONPATH, etc.)
            Map<String, String> env = pb.environment();
            // Add any custom environment variables here if needed
            // env.put("PYTHONPATH", "...");
            
            try {
                process = pb.start();
            } catch (IOException e) {
                // Fallback: try python3 -m datashark.cli serve
                logInfo("Command 'datashark' not found, trying 'python3 -m datashark.cli serve'");
                command.clear();
                command.add("python3");
                command.add("-m");
                command.add("datashark.cli");
                command.add("serve");
                
                pb = new ProcessBuilder(command);
                pb.directory(new java.io.File(System.getProperty("user.home")));
                process = pb.start();
            }
            
            // Get stdin stream (keep it open)
            stdin = process.getOutputStream();
            
            // Start stdout reader thread (for JSON-RPC responses)
            stdoutReaderThread = new Thread(this::readStdout, "DataShark-StdoutReader");
            stdoutReaderThread.setDaemon(true);
            stdoutReaderThread.start();
            
            // Start stderr reader thread (for logging)
            stderrReaderThread = new Thread(this::readStderr, "DataShark-StderrReader");
            stderrReaderThread.setDaemon(true);
            stderrReaderThread.start();
            
            isRunning.set(true);
            logInfo("DataShark Python server started (PID: " + getProcessId() + ")");
            
            // Register shutdown hook
            Runtime.getRuntime().addShutdownHook(new Thread(this::dispose, "DataShark-ShutdownHook"));
        }
    }
    
    /**
     * Send a JSON-RPC request to the DataShark server.
     * 
     * @param method The JSON-RPC method name
     * @param params The method parameters (can be null)
     * @return The request ID (for tracking responses)
     * @throws IOException if the request cannot be sent
     * @throws IllegalStateException if the client is not running
     */
    public int sendRequest(String method, Map<String, Object> params) throws IOException {
        if (!isRunning.get()) {
            throw new IllegalStateException("DataShark client is not running. Call start() first.");
        }
        
        if (stdin == null) {
            throw new IllegalStateException("Process stdin stream is not available");
        }
        
        int requestId;
        synchronized (requestIdLock) {
            requestIdCounter++;
            requestId = requestIdCounter;
        }
        
        // Build JSON-RPC request string manually (to avoid external dependencies)
        String jsonRequest = buildJsonRpcRequest(method, params, requestId);
        
        // Write to stdin (with newline for line-delimited JSON)
        synchronized (stdin) {
            stdin.write((jsonRequest + "\n").getBytes(StandardCharsets.UTF_8));
            stdin.flush();
        }
        
        logInfo("Sent request: " + method + " (id: " + requestId + ")");
        
        return requestId;
    }
    
    /**
     * Build a JSON-RPC request string.
     * 
     * @param method The method name
     * @param params The parameters (can be null)
     * @param id The request ID
     * @return JSON string
     */
    private String buildJsonRpcRequest(String method, Map<String, Object> params, int id) {
        StringBuilder json = new StringBuilder();
        json.append("{");
        json.append("\"jsonrpc\":\"2.0\",");
        json.append("\"method\":").append(escapeJsonString(method)).append(",");
        json.append("\"id\":").append(id);
        
        if (params != null && !params.isEmpty()) {
            json.append(",\"params\":{");
            boolean first = true;
            for (Map.Entry<String, Object> entry : params.entrySet()) {
                if (!first) {
                    json.append(",");
                }
                json.append(escapeJsonString(entry.getKey())).append(":");
                json.append(escapeJsonValue(entry.getValue()));
                first = false;
            }
            json.append("}");
        }
        
        json.append("}");
        return json.toString();
    }
    
    /**
     * Escape a string for JSON.
     */
    private String escapeJsonString(String str) {
        if (str == null) {
            return "null";
        }
        StringBuilder sb = new StringBuilder();
        sb.append("\"");
        for (char c : str.toCharArray()) {
            switch (c) {
                case '"':
                    sb.append("\\\"");
                    break;
                case '\\':
                    sb.append("\\\\");
                    break;
                case '\b':
                    sb.append("\\b");
                    break;
                case '\f':
                    sb.append("\\f");
                    break;
                case '\n':
                    sb.append("\\n");
                    break;
                case '\r':
                    sb.append("\\r");
                    break;
                case '\t':
                    sb.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
                    break;
            }
        }
        sb.append("\"");
        return sb.toString();
    }
    
    /**
     * Escape a value for JSON.
     */
    private String escapeJsonValue(Object value) {
        if (value == null) {
            return "null";
        } else if (value instanceof String) {
            return escapeJsonString((String) value);
        } else if (value instanceof Number || value instanceof Boolean) {
            return value.toString();
        } else if (value instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> map = (Map<String, Object>) value;
            StringBuilder sb = new StringBuilder();
            sb.append("{");
            boolean first = true;
            for (Map.Entry<String, Object> entry : map.entrySet()) {
                if (!first) {
                    sb.append(",");
                }
                sb.append(escapeJsonString(entry.getKey())).append(":");
                sb.append(escapeJsonValue(entry.getValue()));
                first = false;
            }
            sb.append("}");
            return sb.toString();
        } else if (value instanceof List) {
            @SuppressWarnings("unchecked")
            List<Object> list = (List<Object>) value;
            StringBuilder sb = new StringBuilder();
            sb.append("[");
            boolean first = true;
            for (Object item : list) {
                if (!first) {
                    sb.append(",");
                }
                sb.append(escapeJsonValue(item));
                first = false;
            }
            sb.append("]");
            return sb.toString();
        } else {
            // Fallback: convert to string
            return escapeJsonString(value.toString());
        }
    }
    
    /**
     * Dispose of the client and kill the Python process.
     * 
     * This method is idempotent and thread-safe.
     */
    public void dispose() {
        if (!isRunning.get() || isShuttingDown.getAndSet(true)) {
            return;
        }
        
        synchronized (LOCK) {
            if (!isRunning.get()) {
                return;
            }
            
            logInfo("Shutting down DataShark client...");
            
            // Close stdin first (signal server to stop reading)
            if (stdin != null) {
                try {
                    stdin.close();
                } catch (IOException e) {
                    logError("Error closing stdin", e);
                }
            }
            
            // Interrupt reader threads
            if (stdoutReaderThread != null && stdoutReaderThread.isAlive()) {
                stdoutReaderThread.interrupt();
            }
            if (stderrReaderThread != null && stderrReaderThread.isAlive()) {
                stderrReaderThread.interrupt();
            }
            
            // Destroy the process
            if (process != null) {
                try {
                    // Give the process a chance to exit gracefully
                    process.destroy();
                    
                    // Wait up to 2 seconds for graceful shutdown
                    boolean terminated = process.waitFor(2, java.util.concurrent.TimeUnit.SECONDS);
                    
                    if (!terminated) {
                        // Force kill if it didn't exit gracefully
                        logInfo("Process did not exit gracefully, forcing termination...");
                        process.destroyForcibly();
                        process.waitFor(1, java.util.concurrent.TimeUnit.SECONDS);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    logError("Interrupted while waiting for process to terminate", e);
                    if (process != null) {
                        process.destroyForcibly();
                    }
                } catch (Exception e) {
                    logError("Error destroying process", e);
                }
            }
            
            // Wait for reader threads to finish (with timeout)
            if (stdoutReaderThread != null) {
                try {
                    stdoutReaderThread.join(1000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
            if (stderrReaderThread != null) {
                try {
                    stderrReaderThread.join(1000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
            
            isRunning.set(false);
            logInfo("DataShark client shut down complete");
        }
    }
    
    /**
     * Check if the client is currently running.
     * 
     * @return true if the process is running
     */
    public boolean isRunning() {
        return isRunning.get() && process != null && process.isAlive();
    }
    
    /**
     * Get the process ID (if available).
     * 
     * @return Process ID as string, or "unknown" if not available
     */
    private String getProcessId() {
        if (process != null) {
            try {
                // Java 9+ has Process.pid()
                return String.valueOf(process.pid());
            } catch (Exception e) {
                return "unknown";
            }
        }
        return "unknown";
    }
    
    /**
     * Read stdout continuously (for JSON-RPC responses).
     * This runs in a separate daemon thread.
     */
    private void readStdout() {
        if (process == null) {
            return;
        }
        
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            
            String line;
            while (isRunning.get() && !Thread.currentThread().isInterrupted()) {
                try {
                    line = reader.readLine();
                    if (line == null) {
                        // EOF - process has closed stdout
                        logInfo("DataShark process stdout closed");
                        break;
                    }
                    
                    if (line.trim().isEmpty()) {
                        continue;
                    }
                    
                    // Log the response (in production, this might be handled by a response handler)
                    logInfo("Received response: " + line);
                    
                    // TODO: Parse JSON-RPC response and dispatch to appropriate handler
                    // This would require a response callback mechanism
                    
                } catch (IOException e) {
                    if (isRunning.get() && !Thread.currentThread().isInterrupted()) {
                        logError("Error reading stdout", e);
                    }
                    break;
                }
            }
        } catch (IOException e) {
            logError("Error setting up stdout reader", e);
        } finally {
            // If we exit the loop, the process likely died
            if (isRunning.get()) {
                logError("DataShark process stdout reader exited unexpectedly", null);
                isRunning.set(false);
            }
        }
    }
    
    /**
     * Read stderr continuously (for Python server logs).
     * This runs in a separate daemon thread and logs to Eclipse console.
     */
    private void readStderr() {
        if (process == null) {
            return;
        }
        
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getErrorStream(), StandardCharsets.UTF_8))) {
            
            String line;
            while (isRunning.get() && !Thread.currentThread().isInterrupted()) {
                try {
                    line = reader.readLine();
                    if (line == null) {
                        // EOF - process has closed stderr
                        break;
                    }
                    
                    if (line.trim().isEmpty()) {
                        continue;
                    }
                    
                    // Log to Eclipse console (INFO level for Python server logs)
                    logInfo("[DataShark Server] " + line);
                    
                } catch (IOException e) {
                    if (isRunning.get() && !Thread.currentThread().isInterrupted()) {
                        logError("Error reading stderr", e);
                    }
                    break;
                }
            }
        } catch (IOException e) {
            logError("Error setting up stderr reader", e);
        }
    }
    
    /**
     * Log an info message to the Eclipse log.
     */
    private void logInfo(String message) {
        if (log != null && bundle != null) {
            log.log(new Status(Status.INFO, bundle.getSymbolicName(), message));
        } else {
            System.out.println("[DataShark] " + message);
        }
    }
    
    /**
     * Log an error message to the Eclipse log.
     */
    private void logError(String message, Throwable e) {
        if (log != null && bundle != null) {
            log.log(new Status(Status.ERROR, bundle.getSymbolicName(), message, e));
        } else {
            System.err.println("[DataShark ERROR] " + message);
            if (e != null) {
                e.printStackTrace();
            }
        }
    }
}
