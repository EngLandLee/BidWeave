// SPDX-FileCopyrightText: 2026 BidWeave contributors
// SPDX-License-Identifier: Apache-2.0
// Purpose: require service credentials on every Flowable REST operation.
package com.bidweave.workflow;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.NoOpPasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
@SuppressWarnings("deprecation")
public class SecurityConfig {
    @Bean
    UserDetailsService workflowUsers(
            @Value("${FLOWABLE_USER:flowable}") String username,
            @Value("${FLOWABLE_PASSWORD}") String password) {
        return new InMemoryUserDetailsManager(User.withUsername(username)
                .password(password)
                .roles("FLOWABLE")
                .build());
    }

    @Bean
    SecurityFilterChain workflowSecurity(HttpSecurity http) throws Exception {
        http.csrf(csrf -> csrf.disable())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                new AntPathRequestMatcher("/actuator/health"),
                                new AntPathRequestMatcher("/actuator/info")).permitAll()
                        .anyRequest().authenticated())
                .httpBasic(basic -> {});
        return http.build();
    }

    @Bean
    @SuppressWarnings("deprecation")
    org.springframework.security.crypto.password.PasswordEncoder passwordEncoder() {
        return NoOpPasswordEncoder.getInstance();
    }
}
