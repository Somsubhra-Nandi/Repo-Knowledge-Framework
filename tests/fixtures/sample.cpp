#include <iostream>
#include <string>
#include <vector>

namespace services {

class UserService {
public:
    explicit UserService(const std::string& name) : name_(name) {}

    std::string getUser(const std::string& id) const {
        return formatUser(id);
    }

    std::vector<std::string> getAllUsers() const {
        return buildUserList();
    }

private:
    std::string name_;

    std::string formatUser(const std::string& id) const {
        return name_ + ":" + id;
    }

    std::vector<std::string> buildUserList() const {
        std::vector<std::string> list;
        list.push_back(name_);
        return list;
    }
};

struct Config {
    bool debug;
    int max_users;
};

} // namespace services

std::string topLevelHelper(const std::string& text) {
    std::string result = text;
    return result;
}

int main() {
    services::UserService svc("test");
    std::cout << svc.getUser("1") << std::endl;
    return 0;
}
