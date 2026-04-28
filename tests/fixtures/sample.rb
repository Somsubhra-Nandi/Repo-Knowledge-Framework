require 'json'
require_relative 'utils'

class UserService
  def initialize(name)
    @name = name
  end

  def get_user(id)
    format_user(id)
  end

  private

  def format_user(id)
    "#{@name}:#{id}"
  end
end

module Helpers
  def self.top_level_helper(text)
    text.strip
  end
end

def standalone_function(x)
  x.to_s
end
