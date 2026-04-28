#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    char name[256];
    int id;
} User;

char* format_user(User* user) {
    char* result = malloc(512);
    snprintf(result, 512, "%s:%d", user->name, user->id);
    return result;
}

User* get_user(int id) {
    User* user = malloc(sizeof(User));
    user->id = id;
    strcpy(user->name, "default");
    return user;
}

int main(int argc, char* argv[]) {
    User* user = get_user(1);
    char* formatted = format_user(user);
    printf("%s\n", formatted);
    free(formatted);
    free(user);
    return 0;
}
