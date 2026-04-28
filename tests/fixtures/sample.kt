package com.example.service

import java.util.UUID

interface Processor {
    fun process(input: String): String
}

class UserService(private val name: String) : Processor {
    override fun process(input: String): String {
        return formatOutput(input)
    }

    private fun formatOutput(value: String): String {
        return "$name: $value"
    }

    fun getUser(id: String): String {
        return process(id)
    }
}

object ServiceFactory {
    fun create(name: String): UserService {
        return UserService(name)
    }
}

fun topLevelHelper(text: String): String {
    return text.trim()
}
