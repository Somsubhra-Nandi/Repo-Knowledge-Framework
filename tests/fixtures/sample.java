package com.example.service;

import java.util.List;
import java.util.ArrayList;

public class UserService {

    private final String serviceName;

    public UserService(String serviceName) {
        this.serviceName = serviceName;
    }

    public List<String> getUsers() {
        return buildUserList();
    }

    public String getUserById(String id) {
        List<String> users = getUsers();
        return formatUser(id);
    }

    private List<String> buildUserList() {
        List<String> list = new ArrayList<>();
        list.add(this.serviceName);
        return list;
    }

    private String formatUser(String id) {
        return this.serviceName + ":" + id;
    }
}

class HelperService {

    public String process(String input) {
        return input.trim();
    }
}
