package com.datashark.ui.handlers;

import java.io.IOException;

import org.eclipse.core.commands.AbstractHandler;
import org.eclipse.core.commands.ExecutionEvent;
import org.eclipse.core.commands.ExecutionException;
import org.eclipse.jface.dialogs.MessageDialog;
import org.eclipse.ui.IWorkbenchWindow;
import org.eclipse.ui.handlers.HandlerUtil;
import org.eclipse.core.runtime.ILog;
import org.eclipse.core.runtime.Platform;
import org.eclipse.core.runtime.Status;
import org.osgi.framework.Bundle;
import org.osgi.framework.FrameworkUtil;

import com.datashark.ui.client.DataSharkClient;

/**
 * Handler for the DataShark Ping command.
 * 
 * This handler uses the DataSharkClient singleton to send a ping request
 * to the persistent Python server process.
 */
public class PingHandler extends AbstractHandler {

    @Override
    public Object execute(ExecutionEvent event) throws ExecutionException {
        IWorkbenchWindow window = HandlerUtil.getActiveWorkbenchWindowChecked(event);
        
        try {
            // Get the singleton client instance
            DataSharkClient client = DataSharkClient.getInstance();
            
            // Ensure the client is running (start if needed)
            if (!client.isRunning()) {
                logInfo("Starting DataShark client...");
                client.start();
            }
            
            // Send the ping request
            int requestId = client.sendRequest("ping", null);
            
            // Show confirmation (response will appear in Error Log)
            MessageDialog.openInformation(
                    window.getShell(),
                    "DataShark Ping",
                    "Ping request sent to DataShark server (ID: " + requestId + ").\n\n" +
                    "Check the Error Log view for the server response.");

        } catch (IOException e) {
            logError("Failed to send ping request", e);
            MessageDialog.openError(
                    window.getShell(),
                    "DataShark Error",
                    "Failed to send ping request to DataShark server.\n\n" +
                    "Error: " + e.getMessage() + "\n\n" +
                    "See Error Log for details.");
        } catch (IllegalStateException e) {
            logError("DataShark client error", e);
            MessageDialog.openError(
                    window.getShell(),
                    "DataShark Error",
                    "DataShark client is not available.\n\n" +
                    "Error: " + e.getMessage() + "\n\n" +
                    "See Error Log for details.");
        } catch (Exception e) {
            logError("Unexpected error in PingHandler", e);
            MessageDialog.openError(
                    window.getShell(),
                    "DataShark Error",
                    "An unexpected error occurred.\n\n" +
                    "Error: " + e.getMessage() + "\n\n" +
                    "See Error Log for details.");
        }
        
        return null;
    }

    private void logInfo(String message) {
        Bundle bundle = FrameworkUtil.getBundle(this.getClass());
        if (bundle != null) {
            ILog log = Platform.getLog(bundle);
            log.log(new Status(Status.INFO, bundle.getSymbolicName(), message));
        }
    }

    private void logError(String message, Throwable e) {
        Bundle bundle = FrameworkUtil.getBundle(this.getClass());
        if (bundle != null) {
            ILog log = Platform.getLog(bundle);
            log.log(new Status(Status.ERROR, bundle.getSymbolicName(), message, e));
        }
    }
}
