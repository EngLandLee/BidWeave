// SPDX-FileCopyrightText: 2026 BidWeave contributors
// SPDX-License-Identifier: Apache-2.0
// Purpose: start the source-built Flowable process REST service.
package com.bidweave.workflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WorkflowApplication {
    public static void main(String[] args) {
        SpringApplication.run(WorkflowApplication.class, args);
    }
}
