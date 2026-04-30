# EasyBrowser Strategy and Cooling

Two major routing modes are planned:

- strategy mode
  - provider chosen by policy
- direct mode
  - provider forced by caller or operator

Strategy inputs may later include:

- requested capabilities
- provider availability
- cooldown state
- recent failure rate
- operator preference

Cooling behavior may later include:

- provider-level cooldown
- runtime-instance-level cooldown
- exponential or bounded cooldown windows
- recovery probing before re-entry

This skeleton reserves the directories where those policies will live but does
not implement them yet.
