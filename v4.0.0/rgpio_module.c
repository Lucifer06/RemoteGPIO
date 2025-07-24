#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/gpio/driver.h>
#include <linux/platform_device.h>
#include <linux/irq.h>
#include <linux/irqdomain.h>
#include <linux/moduleparam.h>
#include <linux/slab.h> // Required for kzalloc/kfree
#include <linux/bitops.h> // Required for bit operations

#define DRIVER_NAME "rgpio_module"

static int num_gpios = 8; // Default value if not specified

module_param(num_gpios, int, 0644);
MODULE_PARM_DESC(num_gpios, "Number of virtual GPIOs to create (default: 8)");

// The struct now contains storage for the GPIO levels
struct rgpio_chip {
    struct gpio_chip chip;
    struct platform_device *pdev;
    // Use a bitmask to store the level of each GPIO line
    unsigned long *levels;
};

// Function to get the value of a GPIO line
static int rgpio_get(struct gpio_chip *chip, unsigned offset)
{
    struct rgpio_chip *rgpio = gpiochip_get_data(chip);
    // test_bit returns 0 or 1, which is exactly what we need.
    return !!test_bit(offset, rgpio->levels);
}

// Function to set the value of a GPIO line
static void rgpio_set(struct gpio_chip *chip, unsigned offset, int value)
{
    struct rgpio_chip *rgpio = gpiochip_get_data(chip);
    if (value)
        set_bit(offset, rgpio->levels);
    else
        clear_bit(offset, rgpio->levels);
}

// Function to set the direction to input
static int rgpio_direction_input(struct gpio_chip *chip, unsigned offset)
{
    // Nothing special to do for a virtual GPIO, just return success.
    return 0;
}

// Function to set the direction to output
static int rgpio_direction_output(struct gpio_chip *chip, unsigned offset, int value)
{
    // When direction is set to output, set its initial value.
    rgpio_set(chip, offset, value);
    return 0;
}


// Function to trigger an interrupt on a specific line
static ssize_t trigger_irq_store(struct device *dev, struct device_attribute *attr, const char *buf, size_t count) {
    long line;
    int ret;
    struct gpio_chip *chip = dev_get_drvdata(dev);

    ret = kstrtol(buf, 10, &line);
    if (ret) return ret;

    if (line < 0 || line >= num_gpios) {
        dev_err(dev, "Invalid line: %ld\n", line);
        return -EINVAL;
    }

    dev_info(dev, "Triggering virtual interrupt on line %ld\n", line);
    generic_handle_irq(irq_find_mapping(chip->irq.domain, line));

    return count;
}

static DEVICE_ATTR_WO(trigger_irq);

static struct attribute *rgpio_chip_attrs[] = {
    &dev_attr_trigger_irq.attr,
    NULL,
};

static const struct attribute_group rgpio_chip_group = {
    .attrs = rgpio_chip_attrs,
};

// Driver initialization
static int rgpio_probe(struct platform_device *pdev) {
    struct rgpio_chip *rgpio;
    struct irq_domain *irq_domain;
    int ret;

    rgpio = devm_kzalloc(&pdev->dev, sizeof(*rgpio), GFP_KERNEL);
    if (!rgpio) return -ENOMEM;

    // Allocate memory for the GPIO levels bitmask
    rgpio->levels = devm_kzalloc(&pdev->dev, BITS_TO_LONGS(num_gpios) * sizeof(unsigned long), GFP_KERNEL);
    if (!rgpio->levels) return -ENOMEM;

    rgpio->chip.label = DRIVER_NAME;
    rgpio->chip.parent = &pdev->dev;
    rgpio->chip.owner = THIS_MODULE;
    
    // Assign our functions to the gpio_chip structure
    rgpio->chip.get = rgpio_get;
    rgpio->chip.set = rgpio_set;
    rgpio->chip.direction_input = rgpio_direction_input;
    rgpio->chip.direction_output = rgpio_direction_output;

    rgpio->chip.base = -1;
    rgpio->chip.ngpio = num_gpios;
    rgpio->chip.can_sleep = false;

    // Pass rgpio (our full struct) instead of just the chip
    platform_set_drvdata(pdev, rgpio);

    // Create an interrupt domain for our virtual GPIOs
    irq_domain = irq_domain_create_linear(pdev->dev.fwnode, num_gpios, &irq_generic_chip_ops, NULL);
    if (!irq_domain) {
        dev_err(&pdev->dev, "Cannot create IRQ domain\n");
        return -ENOMEM;
    }

    // Associate the interrupt domain with the gpiochip
    ret = gpiochip_irqchip_add_domain(&rgpio->chip, irq_domain);
    if (ret) {
        dev_err(&pdev->dev, "Cannot add irqchip domain\n");
        irq_domain_remove(irq_domain);
        return ret;
    }

    // Register the gpio_chip with the kernel
    // Pass rgpio as the data for gpiochip
    ret = devm_gpiochip_add_data(&pdev->dev, &rgpio->chip, rgpio);
    if (ret < 0) {
        dev_err(&pdev->dev, "Cannot register gpiochip\n");
        return ret;
    }

    // Create our sysfs "trigger_irq" attribute
    ret = sysfs_create_group(&pdev->dev.kobj, &rgpio_chip_group);
    if (ret) {
        dev_err(&pdev->dev, "Cannot create sysfs group\n");
    }

    dev_info(&pdev->dev, "rgpio driver loaded, %d GPIOs created starting from base %d\n", rgpio->chip.ngpio, rgpio->chip.base);
    return 0;
}

static struct platform_driver rgpio_driver = {
    .driver = { .name = DRIVER_NAME, },
    .probe = rgpio_probe,
};

static struct platform_device *rgpio_pdev;

static int __init rgpio_init(void) {
    int ret;
    
    ret = platform_driver_register(&rgpio_driver);
    if (ret) return ret;

    rgpio_pdev = platform_device_alloc(DRIVER_NAME, -1);
    if (!rgpio_pdev) {
        platform_driver_unregister(&rgpio_driver);
        return -ENOMEM;
    }

    ret = platform_device_add(rgpio_pdev);
    if (ret) {
        platform_device_put(rgpio_pdev);
        platform_driver_unregister(&rgpio_driver);
        return ret;
    }

    return 0;
}

static void __exit rgpio_exit(void) {
    platform_device_unregister(rgpio_pdev);
    platform_driver_unregister(&rgpio_driver);
}

module_init(rgpio_init);
module_exit(rgpio_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Frederic Guiot");
MODULE_DESCRIPTION("Virtual GPIO driver for Victron Venus OS with dynamic GPIO count and get/set handlers");

