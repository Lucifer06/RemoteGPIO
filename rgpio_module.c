#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/gpio/driver.h>
#include <linux/platform_device.h>
#include <linux/irq.h>
#include <linux/irqdomain.h>
#include <linux/moduleparam.h> // NOUVEAU : Nécessaire pour les paramètres de module

#define DRIVER_NAME "rgpio_module" // MODIFIÉ : Pour correspondre au nouveau nom

// NOUVEAU : Variable pour stocker le nombre de GPIOs
static int num_gpios = 8; // Valeur par défaut si non spécifiée

// NOUVEAU : Déclaration du paramètre de module
// 'num_gpios' est le nom du paramètre, 'int' est son type, 0644 sont les permissions
module_param(num_gpios, int, 0644);
MODULE_PARM_DESC(num_gpios, "Nombre de GPIOs virtuels à créer (défaut: 8)");

struct rgpio_chip {
    struct gpio_chip chip;
    struct platform_device *pdev;
};

// Fonction pour déclencher une interruption sur une ligne spécifique
static ssize_t trigger_irq_store(struct device *dev, struct device_attribute *attr, const char *buf, size_t count) {
    long line;
    int ret;
    struct gpio_chip *chip = dev_get_drvdata(dev);

    ret = kstrtol(buf, 10, &line);
    if (ret) return ret;

    // MODIFIÉ : Vérifie par rapport au nombre dynamique de GPIOs
    if (line < 0 || line >= num_gpios) {
        dev_err(dev, "Ligne invalide : %ld\n", line);
        return -EINVAL;
    }

    dev_info(dev, "Déclenchement de l'interruption virtuelle sur la ligne %ld\n", line);
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

// Initialisation du driver
static int rgpio_probe(struct platform_device *pdev) {
    struct rgpio_chip *rgpio;
    struct irq_domain *irq_domain;
    int ret;

    rgpio = devm_kzalloc(&pdev->dev, sizeof(*rgpio), GFP_KERNEL);
    if (!rgpio) return -ENOMEM;

    rgpio->chip.label = DRIVER_NAME;
    rgpio->chip.parent = &pdev->dev;
    rgpio->chip.owner = THIS_MODULE;
    rgpio->chip.base = -1;
    rgpio->chip.ngpio = num_gpios; // MODIFIÉ : Utilise notre variable dynamique
    rgpio->chip.can_sleep = false;

    platform_set_drvdata(pdev, &rgpio->chip);

    // Crée un domaine d'interruption pour nos GPIOs virtuels
    irq_domain = irq_domain_create_linear(pdev->dev.fwnode, num_gpios, &irq_generic_chip_ops, NULL); // MODIFIÉ
    if (!irq_domain) {
        dev_err(&pdev->dev, "Impossible de créer le domaine IRQ\n");
        return -ENOMEM;
    }

    ret = gpiochip_irqchip_add_domain(&rgpio->chip, irq_domain);
    if (ret) {
        dev_err(&pdev->dev, "Impossible d'ajouter le domaine irqchip\n");
        irq_domain_remove(irq_domain);
        return ret;
    }

    ret = devm_gpiochip_add_data(&pdev->dev, &rgpio->chip, NULL);
    if (ret < 0) {
        dev_err(&pdev->dev, "Impossible d'enregistrer le gpiochip\n");
        return ret;
    }

    ret = sysfs_create_group(&pdev->dev.kobj, &rgpio_chip_group);
    if (ret) {
        dev_err(&pdev->dev, "Impossible de créer le groupe sysfs\n");
    }

    dev_info(&pdev->dev, "Driver rgpio chargé, %d GPIOs créés à partir de la base %d\n", rgpio->chip.ngpio, rgpio->chip.base);
    return 0;
}

// ... Le reste du fichier (rgpio_driver, rgpio_pdev, rgpio_init, rgpio_exit, etc.) reste identique ...
// ... (Assurez-vous que le DRIVER_NAME est bien "rgpio_module" dans la structure platform_driver) ...
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
MODULE_DESCRIPTION("Virtual GPIO driver for Victron Venus OS with dynamic GPIO count");
